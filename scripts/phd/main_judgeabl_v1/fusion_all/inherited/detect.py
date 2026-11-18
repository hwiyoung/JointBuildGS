"""PHD-MAIN-BASELINES-v1 MVS-based fusion of Zhou et al. (2020), reproduced (order v1.1, 6.5): change detection on the prior surface with the
current training images, then the composite depth of every training view (no training). jointbuildgs:dev, CPU, through run_cpu_bl.sh.

  python mvsfuse/detect.py run <site> <LoD2|ALS> <result> [--nproc 14] [--views N] [--root <dir> --no-depth]
        -> SB/runs/<site>/<result>/depth/<stem>.npy (composite, camera-z metres at 1024 x 741, NaN = none; gpu_bl.py depthfuse reads it),
           detect/detect.json (every '적을 것' of 6.5 and the misses and false detections, colour thresholds 25 / 20 / 30),
           detect/cells.npz (the plan-cell layers), detect/views.json (per view), detect/quicklook.png, receipt.json
  python mvsfuse/detect.py colourref <site> <LoD2|ALS> [--nproc 14]
        -> SB/prep/mvsfuse/colourref_<site>_<prior>.json only (order 5.6 item 4: the RMS colour difference on judged pixels where the MVS depth
           agrees with the prior within tau; not used to choose anything; no change decision is formed or written)

Steps (the rules and values: mf_common.RULE; the pairs: SB/prep/mvsfuse/pairs_<site>.json):
  1 per training view with a pair: re-cast the prior (check = the export prior map), the per-pixel colour test of the prior surface points
    (projection, occlusion in the pair, best 3 x 3 NCC within +-2 px, RMS RGB > 25), the per-pair opening (0.7 x the 2 m relief
    displacement of the pair), the view's per-cell statements; the removed-building hypothesis (ground height) per prior building; the
    per-pixel height differences MVS - prior for the cells (every training view)
  2 the plan cells: the view vote (> half of the paired views judging the cell, >= 2), the removed-building rule (95 %), the growth by MVS
    height differences (1 m ring, > 2 m, 2 m steps, each cell searched once; 1.5 m as reference area), the size filter (2 m x 2 m, 4 m2,
    2 m median height difference unless MVS covers less than half of the component), for thresholds 25 (main), 20 and 30 (reference)
  3 the composite depth (threshold 25) and the counts on the region file's 0.25 m patches (codes 11 / 12 caught and missed, 2 / 3 / 4
    caught falsely, 13 / 14 areas; LoD2 code 11 by the stage-3 8.2 classes)
scientific_verdict: null."""
import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mf_common as M  # noqa: E402

THR = (25.0, 20.0, 30.0)          # main first, then the two reference thresholds
RP, RO, RC, RR, RG, RS = (M.RULE[k] for k in ("pixel", "opening", "cells", "removal", "growth", "size"))
CANDS = sorted([(dy, dx) for dy in range(-2, 3) for dx in range(-2, 3)], key=lambda c: (c[0] ** 2 + c[1] ** 2, abs(c[0]), c[0], c[1]))
DY = np.array([c[0] for c in CANDS], np.int64)
DX = np.array([c[1] for c in CANDS], np.int64)
HB = np.linspace(0.0, 256.0, 1025)      # colour histogram bins (0.25)
G = {}                                  # worker state (set in the parent before the fork)
NTH = 2                                 # Open3D threads per worker
PIECE_CELLS = int(np.ceil(M.PIECE_MIN_M2 / M.CELL ** 2))   # D1015-2: new growth pieces below 1 m2 (< 16 cells) are removed


def ocast(scene, O, D):
    import open3d as o3d
    r = np.concatenate([np.asarray(O, np.float32), np.asarray(D, np.float32)], -1).reshape(-1, 6)
    ans = scene.scene.cast_rays(o3d.core.Tensor(r), nthreads=NTH)
    t = ans["t_hit"].numpy()
    tri = ans["primitive_ids"].numpy().astype(np.int64)
    tri[~np.isfinite(t)] = -1
    return t, tri


def best_match(A, pu, pv, B, u0, v0):
    """correspondence: candidate pixel of image B within +-2 px of (u0, v0) with the largest max(0, NCC) of the 3 x 3 grey patches (ties ->
    the candidate nearest to the projection); returns the RMS RGB difference, the candidate index and the score."""
    Gi, Ii, mi, si = A
    Gj, Ij, mj, sj = B
    N = len(pu)
    Pi = np.stack([Gi[pv + oy, pu + ox] for oy in (-1, 0, 1) for ox in (-1, 0, 1)])
    Wj = np.stack([Gj[v0 + oy, u0 + ox] for oy in range(-3, 4) for ox in range(-3, 4)])
    mu_i, sd_i = mi[pv, pu], si[pv, pu]
    best = np.full(N, -1.0, np.float32)
    bi = np.zeros(N, np.int64)
    for c, (dy, dx) in enumerate(CANDS):
        S = np.zeros(N, np.float32)
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                S += Pi[(oy + 1) * 3 + (ox + 1)] * Wj[(dy + oy + 3) * 7 + (dx + ox + 3)]
        mu_j, sd_j = mj[v0 + dy, u0 + dx], sj[v0 + dy, u0 + dx]
        ok = (sd_i > 1e-3) & (sd_j > 1e-3)
        ncc = np.zeros(N, np.float32)
        ncc[ok] = (S[ok] / 9.0 - mu_i[ok] * mu_j[ok]) / (sd_i[ok] * sd_j[ok])
        score = np.maximum(ncc, 0.0)
        better = score > best
        best = np.where(better, score, best)
        bi = np.where(better, c, bi)
    qy, qx = v0 + DY[bi], u0 + DX[bi]
    rms = np.sqrt(((Ii[pv, pu] - Ij[qy, qx]) ** 2).mean(1))
    return rms.astype(np.float32), bi, best


def image_pack(site, stem):
    I_ = M.read_rgb(site, stem)
    g = M.grey(I_)
    m, s = M.local_stats(g)
    return g, I_, m, s


def removal_occlusion(P, O, dirn, dist, own_b, tol):
    """occlusion of the ground point by the prior buildings other than the tested one (rays pass through the tested building's faces)."""
    sc, tb = P.building_scene()
    occ = np.zeros(len(O), bool)
    o = np.array(O, np.float64)
    rem = np.array(dist, np.float64)
    active = np.arange(len(O))
    for _ in range(12):
        if not len(active):
            break
        t, tri = ocast(sc, o[active], dirn[active])
        hitm = np.isfinite(t) & (t < rem[active] - tol)
        bb = np.where(tri >= 0, tb[np.maximum(tri, 0)], -1)
        occ[active[hitm & (bb != own_b[active])]] = True
        same = hitm & (bb == own_b[active])
        adv = active[same]
        step = t[same].astype(np.float64) + 1e-3
        o[adv] += dirn[adv] * step[:, None]
        rem[adv] -= step
        active = adv
    return occ


def judge(stem):
    t0 = time.time()
    V, P, grid, site, prior = G["V"], G["P"], G["grid"], G["site"], G["prior"]
    pair = G["pairs"].get(stem)
    n = f"{stem}.jpg"
    D = M.load_map(site, prior, "prior", stem).astype(np.float64)
    Mv = M.load_map(site, prior, "mvs", stem).astype(np.float64)
    R = V.rays(n, np.float64)
    C = V.C(n)
    t, tri = ocast(P.scene(), np.broadcast_to(C, R.shape), R)
    t, tri = t.reshape(M.H, M.W), tri.reshape(M.H, M.W)
    hit = np.isfinite(D)
    both = hit & np.isfinite(t)
    ver = dict(mismatch_px=int((hit != np.isfinite(t)).sum()), max_abs_m=float(np.abs(t[both] - D[both]).max()) if both.any() else 0.0)
    tri = np.where(hit, tri, -1)
    idx = np.flatnonzero(hit)
    Rf = R.reshape(-1, 3)
    Xh = C[None, :] + D.ravel()[idx][:, None] * Rf[idx]
    cell_h = grid.cell(Xh)
    out = dict(view=stem, pair=pair, ver=ver, hit_cells=np.unique(cell_h[cell_h >= 0]).astype(np.int64))
    trh = tri.ravel()[idx]
    steep = (trh >= 0) & (P.nz[np.maximum(trh, 0)] < M.STEEP_NZ)           # D1015-1: steep prior faces are not judged (and give no height difference)
    mv = np.isfinite(Mv.ravel()[idx]) & (Mv.ravel()[idx] > 0) & ~steep     # D1015-1b: the cell height difference on the 2.5-D top surface only
    dz = (Mv.ravel()[idx][mv] - D.ravel()[idx][mv]) * Rf[idx][mv, 2]
    keep = cell_h[mv] >= 0
    out["dz_cell"], out["dz"] = cell_h[mv][keep].astype(np.int64), dz[keep].astype(np.float32)
    st = dict(hit_px=int(len(idx)))
    if pair is None or G.get("dz_only"):
        out["stats"] = st
        out["seconds"] = round(time.time() - t0, 2)
        return out
    nj = f"{pair}.jpg"
    A, B = image_pack(site, stem), image_pack(site, pair)
    pv, pu = np.divmod(idx, M.W)
    own = (pu >= 1) & (pu <= M.W - 2) & (pv >= 1) & (pv <= M.H - 2)
    with np.errstate(invalid="ignore", divide="ignore"):
        u, v, z = V.project(nj, Xh)
        u0, v0 = np.floor(u), np.floor(v)
    inframe = (z > 0) & np.isfinite(u0) & np.isfinite(v0) & (u0 >= 3) & (u0 <= M.W - 4) & (v0 >= 3) & (v0 <= M.H - 4)
    st.update(steep_px=int(steep.sum()), steep_not_judged_px=int((own & inframe & steep).sum()))
    k = np.nonzero(own & inframe & ~steep)[0]
    Cj = V.C(nj)
    dvec = Xh[k] - Cj[None, :]
    dist = np.linalg.norm(dvec, axis=1)
    th, _ = ocast(P.scene(), np.broadcast_to(Cj, dvec.shape), dvec / dist[:, None])
    occ = th < dist - RP["occlusion_tolerance_m"]
    kj = k[~occ]
    st.update(own_px=int(own.sum()), in_frame_px=int((own & inframe).sum()), occluded_px=int(occ.sum()), judged_px=int(len(kj)))
    rms, bi, score = best_match(A, pu[kj], pv[kj], B, u0[kj].astype(np.int64), v0[kj].astype(np.int64))
    st["matched_at_projection_share"] = float((bi == 0).mean()) if len(kj) else None
    st["score_zero_share"] = float((score <= 0).mean()) if len(kj) else None
    st["offset_mean_dx_dy_px"] = [float(DX[bi].mean()), float(DY[bi].mean())] if len(kj) else None
    st["offset_within_1px_share"] = float(((np.abs(DX[bi]) <= 1) & (np.abs(DY[bi]) <= 1)).mean()) if len(kj) else None
    # relief displacement of a 2 m height change in this pair (parallax change), the opening size
    smp = kj[np.linspace(0, len(kj) - 1, min(len(kj), 20000)).astype(np.int64)] if len(kj) else kj
    disp = None
    if len(smp):
        X0 = Xh[smp]
        X1 = X0 + np.array([0.0, 0.0, RO["relief_height_m"]])
        ui0, vi0, _ = V.project(n, X0)
        ui1, vi1, _ = V.project(n, X1)
        uj0, vj0, _ = V.project(nj, X0)
        uj1, vj1, _ = V.project(nj, X1)
        disp = float(np.median(np.hypot((uj1 - uj0) - (ui1 - ui0), (vj1 - vj0) - (vi1 - vi0))))
    kk = int(round(RO["factor"] * disp)) if disp is not None else 1
    st.update(relief_disp_px=disp, opening_k=kk)
    import cv2
    judged_img = np.zeros(M.H * M.W, bool)
    judged_img[idx[kj]] = True
    judged_img = judged_img.reshape(M.H, M.W)
    after = []
    for th_ in THR:
        img = np.zeros(M.H * M.W, np.uint8)
        img[idx[kj][rms > th_]] = 1
        img = img.reshape(M.H, M.W)
        if kk >= 2:
            img = cv2.morphologyEx(img, cv2.MORPH_OPEN, np.ones((kk, kk), np.uint8))
        a = (img.ravel()[idx[kj]] > 0)
        after.append(a)
        st[f"change_share_before_{int(th_)}"] = float((rms > th_).mean()) if len(kj) else None
        st[f"change_share_after_{int(th_)}"] = float(a.mean()) if len(kj) else None
    st["change_after_25_px"] = int(after[0].sum())
    cj = cell_h[kj]
    g_ = cj >= 0
    uq, inv = np.unique(cj[g_], return_inverse=True)
    out["vote_cells"] = uq.astype(np.int64)
    out["vote_n"] = np.bincount(inv, minlength=len(uq)).astype(np.int32)
    out["vote_ch"] = np.stack([np.bincount(inv, weights=a[g_].astype(np.float64), minlength=len(uq)) for a in after]).astype(np.int32)
    # colour reference: judged pixels whose MVS depth agrees with the prior within tau (export tau map, depth units)
    T = M.load_map(site, prior, "tau", stem).astype(np.float64).ravel()[idx[kj]]
    mvj = Mv.ravel()[idx[kj]]
    agree = np.isfinite(mvj) & (mvj > 0) & np.isfinite(T) & (np.abs(mvj - D.ravel()[idx[kj]]) <= T)
    out["hist_agree"] = np.histogram(rms[agree], HB)[0].astype(np.int64)
    out["hist_all"] = np.histogram(rms, HB)[0].astype(np.int64)
    st["agree_px"] = int(agree.sum())
    if agree.any():      # exposure context (reference): median signed difference view - pair on the agreeing pixels, per channel
        qy_, qx_ = v0[kj][agree].astype(np.int64) + DY[bi][agree], u0[kj][agree].astype(np.int64) + DX[bi][agree]
        st["agree_signed_rgb_median"] = np.median(A[1][pv[kj][agree], pu[kj][agree]] - B[1][qy_, qx_], axis=0).round(2).tolist()
    # removed-building hypothesis: the pixels on a prior building re-projected through the building's ground height
    nb = G["n_bld"]
    bl = np.where(tri.ravel()[idx] >= 0, G["tri_bld"][np.maximum(tri.ravel()[idx], 0)], -1)
    kb = np.nonzero(own & (bl >= 0) & ~steep)[0]                         # D1015-1 here too
    if len(kb) and nb:
        b = bl[kb]
        hg = G["hg"][b]
        rz = Rf[idx[kb], 2]
        with np.errstate(invalid="ignore", divide="ignore"):
            s = (hg - C[2]) / rz
        okb = np.isfinite(hg) & (rz < -1e-6) & (s > 0)
        kb, b, s = kb[okb], b[okb], s[okb]
        Xg = C[None, :] + s[:, None] * Rf[idx[kb]]
        with np.errstate(invalid="ignore", divide="ignore"):
            ug, vg, zg = V.project(nj, Xg)
            ug0, vg0 = np.floor(ug), np.floor(vg)
        inf_g = (zg > 0) & np.isfinite(ug0) & np.isfinite(vg0) & (ug0 >= 3) & (ug0 <= M.W - 4) & (vg0 >= 3) & (vg0 <= M.H - 4)
        kb, b, Xg, ug0, vg0 = kb[inf_g], b[inf_g], Xg[inf_g], ug0[inf_g], vg0[inf_g]
        dv = Xg - Cj[None, :]
        dd = np.linalg.norm(dv, axis=1)
        occg = removal_occlusion(P, np.broadcast_to(Cj, dv.shape), dv / dd[:, None], dd, b, RP["occlusion_tolerance_m"]) if len(kb) else np.zeros(0, bool)
        kb, b, ug0, vg0 = kb[~occg], b[~occg], ug0[~occg], vg0[~occg]
        rg, _, _ = best_match(A, pu[kb], pv[kb], B, ug0.astype(np.int64), vg0.astype(np.int64))
        out["rem_n"] = np.bincount(b, minlength=nb).astype(np.int64)
        out["rem_sim"] = np.stack([np.bincount(b, weights=(rg <= th_).astype(np.float64), minlength=nb) for th_ in THR]).astype(np.int64)
        st["removal_judged_px"] = int(len(kb))
    out["stats"] = st
    out["seconds"] = round(time.time() - t0, 2)
    return out


# ------------------------------------------------------------------------------------------------ plan-cell steps
def cell_median(cells, vals, n):
    """per-cell median and count of the values (cells < n)."""
    o = np.lexsort((vals, cells))
    c, v = cells[o], vals[o]
    cnt = np.bincount(c, minlength=n)
    start = np.concatenate([[0], np.cumsum(cnt)[:-1]])
    med = np.full(n, np.nan, np.float32)
    has = cnt > 0
    lo = start[has] + (cnt[has] - 1) // 2
    hi = start[has] + cnt[has] // 2
    med[has] = 0.5 * (v[lo] + v[hi])
    return med, cnt


def growth(S, prior_cells, dz, dz_thr, piece_min_cells=PIECE_CELLS):
    """the growth of 6.5: 1 m ring around the change cells, then 2 m around each iteration's new change cells; each cell is searched once."""
    from scipy import ndimage
    S = S.copy()
    searched = S.copy()
    cand = prior_cells & np.isfinite(dz) & (np.abs(np.nan_to_num(dz)) > dz_thr)
    ring = M.dilate(S, RG["ring_m"]) & ~searched
    it, added, per = 0, np.zeros_like(S), []
    while ring.any():
        it += 1
        searched |= ring
        new = ring & cand
        n_raw = int(new.sum())
        if piece_min_cells and new.any():             # D1015-2: 8-connected pieces of the new cells below 1 m2 are removed
            lab, k = ndimage.label(new, structure=np.ones((3, 3), int))
            sz = np.bincount(lab.ravel(), minlength=k + 1)
            new = new & (sz[lab] >= piece_min_cells)
        per.append(dict(iteration=it, searched_cells=int(ring.sum()), new_cells_before_piece_filter=n_raw, new_cells=int(new.sum())))
        if not new.any():
            break
        S |= new
        added |= new
        ring = M.dilate(new, RG["step_m"]) & ~searched
    return S, added, per


def size_filter(S, dz, ny, nx):
    import cv2
    lab, k = M.components(S)
    keep = np.zeros(k + 1, bool)
    comps = []
    if k:
        idx = np.nonzero(lab.ravel())[0]
        l = lab.ravel()[idx]
        iy, ix = np.divmod(idx, nx)
        order = np.argsort(l, kind="stable")
        l, iy, ix, idx = l[order], iy[order], ix[order], idx[order]
        cuts = np.flatnonzero(np.diff(l)) + 1
        for seg in np.split(np.arange(len(l)), cuts):
            c = int(l[seg[0]])
            cx_, cy_ = ix[seg].astype(np.float32), iy[seg].astype(np.float32)
            corners = np.concatenate([np.stack([cx_ + ox, cy_ + oy], 1) for ox in (0, 1) for oy in (0, 1)]) * M.CELL
            (_, _), (rw, rh), ang = cv2.minAreaRect(corners.astype(np.float32))      # D1015-3: the rotated rectangle around the cell corners
            ex, ey = float(min(rw, rh)), float(max(rw, rh))
            area = len(seg) * M.CELL ** 2
            d = dz.ravel()[idx[seg]]
            have = np.isfinite(d)
            no_h = (~have).sum() > 0.5 * len(seg)
            hmed = float(np.median(np.abs(d[have]))) if have.any() else None
            ok = (ex >= RS["min_extent_m"] - 1e-6) and (area >= RS["min_area_m2"]) and (no_h or (hmed is not None and hmed >= RS["min_height_m"]))
            keep[c] = ok
            comps.append(dict(label=c, cells=int(len(seg)), area_m2=round(area, 3), rect_short_m=round(ex, 3), rect_long_m=round(ey, 3),
                              rect_angle_deg=round(float(ang), 1), height_median_abs_m=hmed,
                              cells_without_mvs=int((~have).sum()), kept=bool(ok), kept_without_height=bool(ok and no_h)))
    return keep[lab] & S, comps


def decide(site_state, t_i, extra=True):
    """the plan-cell decision for colour threshold THR[t_i]; returns the final change mask and the record."""
    ss = site_state
    ny, nx = ss["ny"], ss["nx"]
    nsee, nch = ss["nsee"], ss["nch"][t_i]
    vote = ((nsee >= RC["min_views"]) & (2 * nch > nsee)).reshape(ny, nx)
    rem = np.zeros(ny * nx, bool)
    removed = []
    for b in range(ss["n_bld"]):
        nb_, sim = int(ss["rem_n"][b]), int(ss["rem_sim"][t_i][b])
        if nb_ and sim / nb_ >= RR["share"]:
            rem[ss["bcells"][b]] = True
            removed.append(dict(building=b, pixels=nb_, similar_share=round(sim / nb_, 4), cells=int(len(ss["bcells"][b]))))
    rem = rem.reshape(ny, nx)
    tested = [dict(building=b, pixels=int(ss["rem_n"][b]), similar_share=round(int(ss["rem_sim"][t_i][b]) / int(ss["rem_n"][b]), 4))
              for b in range(ss["n_bld"]) if int(ss["rem_n"][b]) > 0]
    S0 = vote | rem
    pc, dz = ss["prior_cells"], ss["dz_med"]
    Sg, added, per = growth(S0, pc, dz, RG["dz_m"])
    final, comps = size_filter(Sg, dz, ny, nx)
    shares = np.array([x["similar_share"] for x in tested]) if tested else np.zeros(0)
    rec = dict(threshold=THR[t_i], vote_cells=int(vote.sum()), removal_added_cells=int((rem & ~vote).sum()), removed_buildings=removed,
               removal_tested=dict(buildings_with_pixels=len(tested), similar_share_quantiles_50_90_max=np.percentile(shares, [50, 90, 100]).round(4).tolist()
                                   if len(shares) else None, largest=sorted(tested, key=lambda x: -x["pixels"])[:12]),
               growth_added_cells=int(added.sum()), growth_iterations=per, before_size_cells=int(Sg.sum()), final_cells=int(final.sum()),
               size_dropped_components=sum(1 for c in comps if not c["kept"]), size_dropped_cells=int(sum(c["cells"] for c in comps if not c["kept"])),
               kept_without_height_components=sum(1 for c in comps if c["kept_without_height"]),
               kept_without_height_cells=int(sum(c["cells"] for c in comps if c["kept_without_height"])), components=comps)
    layers = dict(vote=vote, removal=rem, grown=added, final=final)
    if extra:
        S15, add15, _ = growth(S0, pc, dz, RG["dz_reference_m"])
        f15, _ = size_filter(S15, dz, ny, nx)
        rec["reference"] = dict(growth_dz_1p5m=dict(growth_added_cells=int(add15.sum()), final_cells=int(f15.sum()), final=f15,
                                                    note="order 6.5: the growth with 1.5 m (the paper's pixel threshold was 1.4 / 1.8 m); reference, "
                                                         "areas and the misses / false shares only"))
    return final, rec, layers


def patch_flags(ss, final):
    """per region-file patch: in a change cell (by the patch centre's plan cell), and judged (that cell judged by >= 2 paired views)."""
    c = ss["patch_cell"]
    ok = c >= 0
    inch = np.zeros(len(c), bool)
    inch[ok] = final.ravel()[c[ok]]
    jd = np.zeros(len(c), bool)
    jd[ok] = ss["nsee"][c[ok]] >= RC["min_views"]
    return inch, jd


def counts(ss, final):
    """6.5 '판정의 놓침과 잘못 잡음' per region-file 0.25 m patch (code_ext_v3, evaluation range), the patch in a change cell by its centre;
    shares by area (as the judgment-swapped variant, judgefuse.misses): caught = code 11 / 12 in change; missed = not in change, split into
    'judged no change' (the centre cell judged by >= 2 paired views: the vote said no change; the variant's 'agree') and 'not judged'
    (fewer than 2 paired views: no decision; the variant's 'undecided'); false = code 2 / 3 / 4 in change; codes 13 / 14 area and the
    in-change share. LoD2 code 11 also by stage 3's 8.2 classes; code-11 patches without metric rows apart ('참값 행 없음')."""
    Rg = ss["regions"]
    inch, jd = patch_flags(ss, final)
    ev = Rg["in_eval"]
    code = Rg["code_ext_v3"]
    area = Rg["area"].astype(np.float64)
    parts = dict(change=inch, judged_no_change=~inch & jd, not_judged=~inch & ~jd)

    def row(m):
        r = dict(patches=int(m.sum()), area_m2=round(float(area[m].sum()), 3))
        for k, f in parts.items():
            r[f"{k}_patches"] = int((m & f).sum())
            r[f"{k}_m2"] = round(float(area[m & f].sum()), 3)
            r[f"{k}_share"] = round(float(area[m & f].sum() / area[m].sum()), 5) if m.any() and area[m].sum() > 0 else None
        return r
    t = {str(k): row(ev & (code == k)) for k in (0, 2, 3, 4, 5, 11, 12, 13, 14)}

    def sh(codes, what):
        m = ev & np.isin(code, codes)
        r = row(m)
        return dict(area_m2=r["area_m2"], patches=r["patches"], part_m2=r[f"{what}_m2"], part_patches=r[f"{what}_patches"], share=r[f"{what}_share"])
    out = dict(code_table=t,
               caught={"11": sh((11,), "change"), "12": sh((12,), "change"), "11+12": sh((11, 12), "change")},
               missed={"11": sh((11,), "judged_no_change"), "12": sh((12,), "judged_no_change"), "11+12": sh((11, 12), "judged_no_change")},
               missed_not_judged={"11": sh((11,), "not_judged"), "12": sh((12,), "not_judged"), "11+12": sh((11, 12), "not_judged")},
               false={"2": sh((2,), "change"), "3": sh((3,), "change"), "4": sh((4,), "change"), "2+4": sh((2, 4), "change"),
                      "2+3+4": sh((2, 3, 4), "change")},
               code13=sh((13,), "change"), code14=sh((14,), "change"),
               rule="area shares of the evaluation-range patches; 'missed' = not in change although the centre cell was judged by >= 2 paired views; "
                    "'missed_not_judged' = not in change and fewer than 2 paired views judged the centre cell (both are 6.5's 놓친 변화)")
    if ss.get("lod2_cls") is not None:
        sp = {}
        cls11 = ss["lod2_cls"][11]
        m11 = ev & (code == 11)
        lab = np.full(len(code), "", object)
        for p_, v_ in cls11.items():
            lab[p_] = v_
        mr = ss["main_rows11"]
        for name, key in (("real_change", "real_change"), ("representation", "representation"), ("undecided", "undecided"), ("no_rows", "")):
            mk = m11 & (lab == key)
            sp[name] = row(mk)
            sp[name].update(main_rows=int(mr[mk].sum()), change_main_rows=int(mr[mk & inch].sum()))
        out["lod2_split_8_2"] = dict(classes=sp, names_ko={"real_change": "실제 변화로 봄", "representation": "표현 차이로 봄", "undecided": "가르지 못함",
                                                         "no_rows": "참값 행 없음"},
                                     note="code-11 patches of the evaluation range by stage 3's 8.2 classes (measure8_s3.change's rule, mf_common."
                                          "lod2_change_classes); 'no_rows' = code-11 patches without metric rows (not classified by 8.2); main_rows = "
                                          "the patches' thinned code-11 rows with |s_W| >= 0.2 m (the inflow sample of 8.1 / 8.2), change_main_rows = those "
                                          "of patches in change")
    return out


OFF, MUL = 100_000, 200_000          # the variant's plan-cell key (judgefuse.cell_keys): (floor(x / 0.25) + OFF) * MUL + (floor(y / 0.25) + OFF)


def cell_keys(xy):
    ix = np.floor(xy[:, 0] / M.CELL).astype(np.int64)
    iy = np.floor(xy[:, 1] / M.CELL).astype(np.int64)
    return (ix + OFF) * MUL + (iy + OFF)


def key_centres(k):
    return np.stack([(k // MUL - OFF + 0.5) * M.CELL, (k % MUL - OFF + 0.5) * M.CELL], 1)


def boundary_lfl(xy, area, is_ch):
    """= judgefuse.boundary: 0.25 m plan cells of the patches (by the patch centre); a change cell = change area > half of the cell's patch
    area; boundary = 4-neighbour edges change cell - non-change cell with patches, x 0.25 m (edges to cells without patches apart)."""
    if not len(xy):
        return dict(cells=0, change_cells=0, boundary_m=0.0, boundary_to_cells_without_patch_m=0.0)
    k = cell_keys(xy)
    uk, inv = np.unique(k, return_inverse=True)
    tot = np.bincount(inv, weights=area)
    cf = np.bincount(inv, weights=area * is_ch)
    cc = cf > 0.5 * tot
    ck, rk = uk[cc], uk[~cc]
    e_rest = e_none = 0
    for dk in (MUL, -MUL, 1, -1):
        nb = ck + dk
        in_rest = np.isin(nb, rk)
        e_rest += int(in_rest.sum())
        e_none += int((~in_rest & ~np.isin(nb, ck)).sum())
    return dict(cells=int(len(uk)), change_cells=int(cc.sum()), change_cells_m2=float(cc.sum() * M.CELL ** 2), edges=e_rest,
                boundary_m=float(e_rest * M.CELL), edges_to_cells_without_patch=e_none, boundary_to_cells_without_patch_m=float(e_none * M.CELL))


def records(ss, final, layers, comp, grid):
    """6.5 '적을 것' (threshold 25), aligned with the judgment-swapped variant's definitions (judgefuse.pixel_records, judgefuse.boundary) so
    that 7.4 compares like for like, plus this reproduction's own plan-cell records."""
    ny, nx = ss["ny"], ss["nx"]
    ev = ss["in_eval"]
    pc = ss["prior_cells"]
    A = M.CELL ** 2
    Rg = ss["regions"]
    area = Rg["area"].astype(np.float64)
    pe = Rg["in_eval"]
    inch, _ = patch_flags(ss, final)
    ce = pe & inch
    # per-patch pixel and MVS-pixel sums over the training views (unit map = export locmap), as judgefuse.scan
    nU = len(area)
    pix = np.zeros(nU, np.int64)
    mvs = np.zeros(nU, np.int64)
    for r in comp:
        np.add.at(pix, r["patch_ids"], r["patch_px"])
        np.add.at(mvs, r["patch_ids"], r["patch_mvs"])
    seen = pix > 0
    full_empty = ce & seen & (mvs == 0)
    w = np.where(seen, 1.0 - mvs / np.maximum(pix, 1), 0.0)
    tot = {k: int(sum(r[k] for r in comp)) for k in ("pixels", "prior_px", "prior_kept_px", "replaced_by_mvs_px", "emptied_px", "filled_from_mvs_px",
                                                      "empty_without_prior_px", "change_px")}
    fk = np.unique(np.concatenate([r["filled_keys"] for r in comp])) if comp else np.zeros(0, np.int64)
    fk_eval = fk[grid.eval_mask(key_centres(fk))] if len(fk) else fk
    # this reproduction's plan-cell seam: 4-neighbour edges between a final change cell and a non-change prior cell (any view's prior hit)
    other = pc & ~final
    seam = seam_eval = 0
    for a, b, e in ((final[:, :-1], other[:, 1:], ev[:, :-1]), (final[:, 1:], other[:, :-1], ev[:, 1:]), (final[:-1, :], other[1:, :], ev[:-1, :]),
                    (final[1:, :], other[:-1, :], ev[1:, :])):
        seam += int((a & b).sum())
        seam_eval += int((a & b & e).sum())
    dzc = ss["dz_cnt"].reshape(ny, nx)
    return dict(
        change_area_share=dict(patch_area_share_eval=round(float(area[ce].sum() / area[pe].sum()), 5) if pe.any() else None,
                               change_patch_area_eval_m2=round(float(area[ce].sum()), 3), patch_area_eval_m2=round(float(area[pe].sum()), 3),
                               rule="area of the evaluation-range patches whose centre lies in a change cell / area of all evaluation-range patches "
                                    "(= the variant's conflict area share with 'in change' for 'judged conflict')",
                               plan_cells=dict(change_cells_eval_m2=round(float((final & ev).sum() * A), 2), prior_cells_eval_m2=round(float((pc & ev).sum() * A), 2),
                                               share=round(float((final & ev).sum() / max((pc & ev).sum(), 1)), 5),
                                               change_cells_outside_eval_m2=round(float((final & ~ev).sum() * A), 2))),
        growth_added_m2=dict(all=round(float(layers["grown"].sum() * A), 2), in_eval=round(float((layers["grown"] & ev).sum() * A), 2),
                             in_final_in_eval=round(float((layers["grown"] & final & ev).sum() * A), 2)),
        removal_added_m2=dict(all=round(float((layers["removal"] & ~layers["vote"]).sum() * A), 2),
                              in_eval=round(float((layers["removal"] & ~layers["vote"] & ev).sum() * A), 2)),
        vote_m2=dict(all=round(float(layers["vote"].sum() * A), 2), in_eval=round(float((layers["vote"] & ev).sum() * A), 2)),
        emptied=dict(pixels=tot["emptied_px"], share_of_change_px=round(tot["emptied_px"] / tot["change_px"], 5) if tot["change_px"] else None,
                     share_of_prior_px=round(tot["emptied_px"] / tot["prior_px"], 6) if tot["prior_px"] else None,
                     fully_emptied_patches_eval=int(full_empty.sum()), fully_emptied_area_eval_m2=round(float(area[full_empty].sum()), 3),
                     pixel_weighted_area_eval_m2=round(float((area * w)[ce].sum()), 3), change_patches_eval_without_pixels=int((ce & ~seen).sum()),
                     plan_cells_change_without_any_mvs_m2=dict(all=round(float((final & (dzc == 0)).sum() * A), 2),
                                                               in_eval=round(float((final & (dzc == 0) & ev).sum() * A), 2)),
                     rule="as judgefuse.pixel_records: (a) change patches of the evaluation range on which no training view has an MVS pixel "
                          "(unit-map pixels), (b) their area weighted by the share of their pixels without MVS; plus the plan cells (this reproduction)"),
        mvs_filled=dict(pixels=tot["filled_from_mvs_px"], share_of_all_px=round(tot["filled_from_mvs_px"] / tot["pixels"], 6),
                        plan_cells_eval=int(len(fk_eval)), area_eval_m2=float(len(fk_eval) * A), plan_cells_all=int(len(fk)),
                        rule="as judgefuse.scan: plan cells floor(x / 0.25), floor(y / 0.25) of camera centre + MVS depth x the float32 camera-z ray "
                             "(common.Views.rays) of the pixels without prior depth; cells whose centre is in the evaluation range"),
        boundary=dict(eval=boundary_lfl(Rg["centre"][pe, :2], area[pe], inch[pe].astype(np.float64)),
                      whole_box=boundary_lfl(Rg["centre"][:, :2], area, inch.astype(np.float64)),
                      rule="= judgefuse.boundary with 'in change' for 'judged conflict'",
                      plan_cell_seam=dict(all_m=round(seam * M.CELL, 2), eval_m=round(seam_eval * M.CELL, 2),
                                          rule="this reproduction's own: 4-neighbour edges between a final change cell and a non-change cell with a prior "
                                               "hit of any training view, x 0.25 m ('eval': the change cell in the range)")),
        composite_pixels=tot)


def compose(stem):
    V, grid, site, prior = G["V"], G["grid"], G["site"], G["prior"]
    n = f"{stem}.jpg"
    D = M.load_map(site, prior, "prior", stem).astype(np.float64)
    Mv = M.load_map(site, prior, "mvs", stem).astype(np.float64)
    LM = np.load(M.S0 / "fork_inputs/s61" / site / "maps" / f"locmap_{prior}" / f"{stem}.npy")
    hit = np.isfinite(D) & (D > 0)
    mvs_ok = np.isfinite(Mv) & (Mv > 0)
    R = V.rays(n, np.float64)
    C = V.C(n)
    idx = np.flatnonzero(hit)
    X = C[None, :] + D.ravel()[idx][:, None] * R.reshape(-1, 3)[idx]
    cell = grid.cell(X)
    chg_h = np.zeros(len(idx), bool)
    chg_h[cell >= 0] = G["final_flat"][cell[cell >= 0]]
    chg = np.zeros(M.H * M.W, bool)
    chg[idx[chg_h]] = True
    chg = chg.reshape(M.H, M.W)
    mv = np.where(mvs_ok, Mv, np.nan)
    out = np.where(hit, np.where(chg, mv, D), mv).astype(np.float32)
    if G.get("depth_dir") is not None:
        np.save(G["depth_dir"] / f"{stem}.npy", out)
    nop = ~hit & mvs_ok
    R32 = V.rays(n)                               # float32 rays, as judgefuse.scan, for the MVS-filled plan cells
    Xn = C[None, :] + Mv[nop][:, None] * R32[nop].astype(np.float64)
    loc = LM >= 0
    pu_, pc_ = np.unique(LM[loc], return_counts=True)
    pm_ = np.bincount(np.searchsorted(pu_, LM[loc & mvs_ok]), minlength=len(pu_)) if len(pu_) else np.zeros(0, np.int64)
    return dict(view=stem, pixels=int(LM.size), prior_px=int(hit.sum()), prior_kept_px=int((hit & ~chg).sum()), replaced_by_mvs_px=int((chg & mvs_ok).sum()),
                emptied_px=int((chg & ~mvs_ok).sum()), filled_from_mvs_px=int(nop.sum()), empty_without_prior_px=int((~hit & ~mvs_ok).sum()),
                change_px=int(chg.sum()), filled_keys=np.unique(cell_keys(Xn[:, :2])) if len(Xn) else np.zeros(0, np.int64),
                patch_ids=pu_.astype(np.int64), patch_px=pc_.astype(np.int64), patch_mvs=pm_.astype(np.int64))


def quicklook(path, ss, final, layers, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ny, nx = ss["ny"], ss["nx"]
    img = np.ones((ny, nx, 3))
    img[ss["prior_cells"]] = (0.85, 0.85, 0.85)
    img[layers["vote"] & ~final] = (0.95, 0.65, 0.2)
    img[layers["removal"] & ~layers["vote"] & ~final] = (0.6, 0.3, 0.8)
    img[layers["grown"] & ~final] = (0.3, 0.6, 0.95)
    img[final] = (0.8, 0.05, 0.05)
    fig, ax = plt.subplots(figsize=(8, 8 * ny / nx))
    ax.imshow(img, origin="lower", extent=(ss["lo"][0], ss["lo"][0] + nx * M.CELL, ss["lo"][1], ss["lo"][1] + ny * M.CELL))
    ev = ss["in_eval"]
    ax.contour(ev.astype(float), levels=[0.5], colors="k", linewidths=0.8, origin="lower",
               extent=(ss["lo"][0], ss["lo"][0] + nx * M.CELL, ss["lo"][1], ss["lo"][1] + ny * M.CELL))
    ax.set_title(title, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "colourref"])
    ap.add_argument("site")
    ap.add_argument("prior", choices=["LoD2", "ALS"])
    ap.add_argument("result", nargs="?", default=None)
    ap.add_argument("--nproc", type=int, default=14)
    ap.add_argument("--views", type=int, default=0, help="first N training views only (code test; never a result)")
    ap.add_argument("--root", default=None, help="output root instead of SB/runs/<site>/<result> (preparation re-runs)")
    ap.add_argument("--no-depth", action="store_true", help="do not write the composite depth maps (the composite counts are still made)")
    a = ap.parse_args()
    if a.mode == "colourref":
        return unit(a)
    if not a.result:
        raise SystemExit("run needs a result name")
    RD = Path(a.root) if a.root else M.SB / "runs" / a.site / a.result
    T0 = time.time()
    try:
        rec = unit(a, RD)
    except BaseException as e:  # noqa: BLE001  (the receipt and progress.md record the failure; the error is raised again)
        M.jdump(RD / "receipt.json", dict(site=a.site, result=a.result, scene_prior=a.prior, iteration=0, status="FAILED", error=repr(e)[:2000],
                                          seconds=dict(all=round(time.time() - T0, 1)), rules=M.RULE, decisions_1015=M.DECISIONS_1015,
                                          scientific_verdict=None))
        progress(f"{M.SITE_KO.get(a.site, a.site)} {a.prior} {a.result} 판정과 합친 깊이 (실패: {type(e).__name__}, {round(time.time() - T0)}초)")
        raise
    progress(f"{M.SITE_KO.get(a.site, a.site)} {a.prior} {a.result} 판정과 합친 깊이{'(깊이 파일 쓰지 않음, 준비 다시 돌림)' if a.no_depth else ''} "
             f"(끝, 투표 {rec['vote_m2']:.1f} m²·넓히기 {rec['grown_m2']:.1f} m²·최종 {rec['final_m2']:.1f} m², {round(time.time() - T0)}초)")


def progress(text):
    """one line in SB/progress.md under logs/progress.lock (Korean time)."""
    import datetime as dt
    import fcntl
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    line = f"- {now:%m-%d %H:%M} MVS 기반 결합: {text}\n"
    with open(M.SB / "logs/progress.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        with open(M.SB / "progress.md", "a") as f:
            f.write(line)
        fcntl.flock(lk, fcntl.LOCK_UN)


def unit(a, RD=None):
    T0 = time.time()
    times = {}
    site, prior = a.site, a.prior
    V, train, test = M.views(site)
    if a.views:
        train = train[:a.views]
    pj = json.loads((M.SB / "prep/mvsfuse" / f"pairs_{site}.json").read_text())
    pairs = {r["view"]: r["pair"] for r in pj["pairs"]}
    P = M.Prior(site, prior)
    grid = M.Grid(site)
    # building regions: plan cells and ground height
    t = time.time()
    bcells, hg, binfo = [], np.full(max(P.n_bld, 1), np.nan), []
    if prior == "ALS":
        gsel = ~P.building_tri
        cen = P.V[P.F[gsel]].mean(1)
        gcell = grid.cell(cen)
    for b in range(P.n_bld):
        tb = np.nonzero(P.tri_bld == b)[0]
        cb = M.raster_triangles(grid, P.V, P.F[tb])
        bcells.append(cb)
        if prior == "LoD2":
            walls = tb[P.tri_type[tb] == 1]
            lows = [float(P.V[P.F[walls[P.tri_surface[walls] == s_]]].reshape(-1, 3)[:, 2].min()) for s_ in np.unique(P.tri_surface[walls])]
            hg[b] = float(np.median(lows)) if lows else np.nan
            binfo.append(dict(building=b, name=P.building_names[b] if P.building_names and b < len(P.building_names) else None, triangles=int(len(tb)),
                              cells=int(len(cb)), wall_surfaces=len(lows), ground_m=None if not lows else round(hg[b], 3)))
        else:
            mk = np.zeros(grid.n, bool)
            mk[cb] = True
            ring = M.dilate(mk.reshape(grid.ny, grid.nx), RR["band_m"]).ravel() & ~mk
            sel = (gcell >= 0) & ring[np.maximum(gcell, 0)]
            hg[b] = float(np.median(cen[sel, 2])) if sel.any() else np.nan
            binfo.append(dict(building=b, triangles=int(len(tb)), cells=int(len(cb)), band_ground_triangles=int(sel.sum()),
                              ground_m=None if not sel.any() else round(hg[b], 3)))
    times["buildings_s"] = round(time.time() - t, 1)
    G.update(V=V, P=P, grid=grid, site=site, prior=prior, pairs=pairs, n_bld=P.n_bld, tri_bld=P.tri_bld, hg=hg, dz_only=False)
    M.log(site, prior, "buildings", P.n_bld, "views", len(train), "paired", sum(1 for s in train if pairs.get(s)))
    # step 1: per view
    t = time.time()
    ctx = mp.get_context("fork")
    with ctx.Pool(a.nproc) as pool:
        res = pool.map(judge, train, chunksize=1)
    times["views_s"] = round(time.time() - t, 1)
    M.log("views done", times["views_s"])
    ver_bad = [r["view"] for r in res if r["ver"]["mismatch_px"] > 0.001 * M.H * M.W or r["ver"]["max_abs_m"] > 0.01]
    ver = dict(views=len(res), max_mismatch_px=max(r["ver"]["mismatch_px"] for r in res), max_abs_m=max(r["ver"]["max_abs_m"] for r in res), views_failing=ver_bad)
    if ver_bad:
        M.jdump(M.SB / "prep/mvsfuse" / f"STOP_recast_{site}_{prior}.json", dict(ver=ver, scientific_verdict=None))
        raise SystemExit(f"the re-cast prior differs from the export prior map in {len(ver_bad)} views: stop")
    paired = [r for r in res if r["pair"] is not None and "vote_cells" in r]
    hist_a = np.sum([r["hist_agree"] for r in paired], 0) if paired else np.zeros(len(HB) - 1)
    hist_all = np.sum([r["hist_all"] for r in paired], 0) if paired else np.zeros(len(HB) - 1)

    def hq(h):
        c = np.cumsum(h)
        if c[-1] == 0:
            return None
        mids = 0.5 * (HB[1:] + HB[:-1])
        return {f"q{int(q * 100)}": round(float(mids[np.searchsorted(c, q * c[-1])]), 2) for q in (0.05, 0.25, 0.5, 0.75, 0.95, 0.99)}
    colour = dict(rule="order 5.6 item 4 (reference only): RMS RGB difference at the correspondence of the judged pixels whose MVS depth agrees with "
                       "the prior within tau (export tau map); histogram bins 0.25", agree_pixels=int(hist_a.sum()), agree_quantiles=hq(hist_a),
                  all_judged_pixels=int(hist_all.sum()), all_judged_quantiles=hq(hist_all),
                  share_agree_above={str(int(th_)): round(float(hist_a[HB[:-1] >= th_].sum() / max(hist_a.sum(), 1)), 4) for th_ in THR},
                  share_all_above={str(int(th_)): round(float(hist_all[HB[:-1] >= th_].sum() / max(hist_all.sum(), 1)), 4) for th_ in THR})
    pstats = [dict(view=r["view"], pair=r["pair"], seconds=r["seconds"], **r["stats"]) for r in res]
    ks = [s_["opening_k"] for s_ in pstats if s_.get("opening_k") is not None and s_.get("relief_disp_px") is not None]
    ds = [s_["relief_disp_px"] for s_ in pstats if s_.get("relief_disp_px") is not None]
    opening = dict(relief_disp_px_quantiles_5_50_95=np.percentile(ds, [5, 50, 95]).round(2).tolist() if ds else None,
                   k_counts={str(k): int(sum(1 for x in ks if x == k)) for k in sorted(set(ks))}, pairs_without_opening=int(sum(1 for x in ks if x < 2)))
    if a.mode == "colourref":
        out = dict(site=site, prior=prior, colour=colour, opening=opening, recast_check=ver, training_views=len(train), paired_views=len(paired),
                   seconds=dict(**times, all=round(time.time() - T0, 1)), scientific_verdict=None)
        M.jdump(M.SB / "prep/mvsfuse" / f"colourref_{site}_{prior}.json", out)
        M.log(json.dumps(dict(site=site, prior=prior, colour=colour["agree_quantiles"], all=colour["all_judged_quantiles"], s=out["seconds"])))
        return
    # step 2: plan cells
    t = time.time()
    n = grid.n
    nsee = np.zeros(n, np.int64)
    nch = np.zeros((len(THR), n), np.int64)
    for r in paired:
        c = r["vote_cells"]
        nsee[c] += 1
        nch[:, c] += (2 * r["vote_ch"] > r["vote_n"][None, :]).astype(np.int64)
    prior_cells = np.zeros(n, bool)
    for r in res:
        prior_cells[r["hit_cells"]] = True
    dz_cell = np.concatenate([r["dz_cell"] for r in res])
    dz_val = np.concatenate([r["dz"] for r in res])
    dz_med, dz_cnt = cell_median(dz_cell, dz_val, n)
    del dz_cell, dz_val
    rem_n = np.sum([r["rem_n"] for r in paired if "rem_n" in r], 0) if any("rem_n" in r for r in paired) else np.zeros(max(P.n_bld, 1), np.int64)
    rem_sim = np.sum([r["rem_sim"] for r in paired if "rem_sim" in r], 0) if any("rem_sim" in r for r in paired) else np.zeros((len(THR), max(P.n_bld, 1)), np.int64)
    Rg = dict(np.load(M.S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz"))
    ss = dict(ny=grid.ny, nx=grid.nx, lo=grid.lo, nsee=nsee, nch=nch, n_bld=P.n_bld, rem_n=rem_n, rem_sim=rem_sim, bcells=bcells,
              prior_cells=prior_cells.reshape(grid.ny, grid.nx), dz_med=dz_med.reshape(grid.ny, grid.nx), dz_cnt=dz_cnt, in_eval=grid.in_eval,
              regions=Rg, patch_cell=grid.cell(Rg["centre"]), lod2_cls=M.lod2_change_classes(site) if prior == "LoD2" else None)
    if prior == "LoD2":
        rw = np.load(M.S1 / "defs" / site / "rows_LoD2.npz")
        mk_ = rw["thin"] & (np.abs(rw["sW"]) >= 0.2) & (rw["code"] == 11)
        ss["main_rows11"] = np.bincount(rw["patch"][mk_].astype(np.int64), minlength=len(Rg["area"]))
    decisions = {}
    pflags = {}
    for t_i, th_ in enumerate(THR):
        final, rec, layers = decide(ss, t_i, extra=(t_i == 0))
        rec["counts"] = counts(ss, final)
        pflags[f"in_change_{int(th_)}"], pflags["judged"] = patch_flags(ss, final)
        if t_i == 0:
            main_final, main_layers = final, layers
            ref = rec["reference"]["growth_dz_1p5m"]
            c15 = counts(ss, ref.pop("final"))
            ref.update(final_m2=round(ref["final_cells"] * M.CELL ** 2, 2), caught_11_12=c15["caught"]["11+12"]["share"],
                       missed_11_12=c15["missed"]["11+12"]["share"], missed_not_judged_11_12=c15["missed_not_judged"]["11+12"]["share"],
                       false_2_3_4=c15["false"]["2+3+4"]["share"], false_3=c15["false"]["3"]["share"],
                       lod2_real_change_caught=(c15.get("lod2_split_8_2") or {}).get("classes", {}).get("real_change", {}).get("change_share"))
        decisions[str(int(th_))] = rec
    times["cells_s"] = round(time.time() - t, 1)
    # step 3: composite depth (threshold 25) and the records that need it
    t = time.time()
    if not a.no_depth:
        (RD / "depth").mkdir(parents=True, exist_ok=True)
    (RD / "detect").mkdir(parents=True, exist_ok=True)
    G.update(final_flat=main_final.ravel(), depth_dir=None if a.no_depth else RD / "depth")
    with ctx.Pool(a.nproc) as pool:
        comp = pool.map(compose, train, chunksize=2)
    times["compose_s"] = round(time.time() - t, 1)
    A = M.CELL ** 2
    rec0 = decisions["25"]
    rec0["records"] = records(ss, main_final, main_layers, comp, grid)
    rec0["records"].update(views_without_pair=int(sum(1 for s in train if not pairs.get(s))),
                           thresholds=dict(colour=THR[0], colour_reference=list(THR[1:]), height_m=RG["dz_m"], height_reference_m=RG["dz_reference_m"],
                                           opening=opening))
    filled = np.zeros(n, bool)
    fk = np.unique(np.concatenate([r["filled_keys"] for r in comp]))
    fxy = key_centres(fk)
    fc = grid.cell(fxy)
    filled[fc[fc >= 0]] = True
    filled = filled.reshape(grid.ny, grid.nx)
    np.savez_compressed(RD / "detect/cells.npz", lo=grid.lo, cell=M.CELL, nx=grid.nx, ny=grid.ny, nsee=nsee.reshape(grid.ny, grid.nx).astype(np.int32),
                        nch=nch.reshape(len(THR), grid.ny, grid.nx).astype(np.int32), thresholds=np.array(THR), prior_cells=ss["prior_cells"],
                        dz_med=ss["dz_med"], dz_cnt=dz_cnt.reshape(grid.ny, grid.nx).astype(np.int32), in_eval=grid.in_eval, vote=main_layers["vote"],
                        removal=main_layers["removal"], grown=main_layers["grown"], final=main_final, filled_from_mvs=filled)
    cls82 = np.zeros(len(Rg["area"]), np.int8)
    if ss["lod2_cls"] is not None:
        for code_ in (11, 13):
            for p_, v_ in ss["lod2_cls"][code_].items():
                cls82[p_] = {"representation": 1, "real_change": 2, "undecided": 3}[v_]
    np.savez_compressed(RD / "detect/patches.npz", patch_cell=ss["patch_cell"], in_eval=Rg["in_eval"], code_ext_v3=Rg["code_ext_v3"], area=Rg["area"],
                        class_8_2=cls82, class_codes=np.array(["none", "representation", "real_change", "undecided"]), **pflags)
    M.jdump(RD / "detect/views.json", dict(site=site, prior=prior, views=pstats,
                                          compose=[{k: v for k, v in r.items() if k not in ("filled_keys", "patch_ids", "patch_px", "patch_mvs")} for r in comp],
                                          scientific_verdict=None))
    try:
        quicklook(RD / "detect/quicklook.png", ss, main_final, main_layers,
                  f"{site} {prior} {a.result}: red final change; dropped by the size filter: orange voted, purple removal, blue grown; grey prior (not a result)")
    except Exception as e:  # noqa: BLE001
        M.log("quicklook failed", repr(e))
    times["all_s"] = round(time.time() - T0, 1)
    det = dict(site=site, prior=prior, result=a.result, rule=M.RULE, pairs_file=str(M.SB / "prep/mvsfuse" / f"pairs_{site}.json"),
               training_views=len(train), paired_views=len(paired), buildings=binfo, recast_check=ver, colour_reference=colour,
               decisions=decisions, seconds=times, scientific_verdict=None)
    M.jdump(RD / "detect/detect.json", det)
    rc = dict(site=site, result=a.result, method="MVS 기반 결합 (Zhou 외 2020 재현)", scene_prior=prior, iteration=0, status="PASS",
              depth_dir=None if a.no_depth else str(RD / "depth"), rules=M.RULE, decisions_1015=M.DECISIONS_1015,
              rule_values=dict(colour_threshold=THR[0], colour_reference=list(THR[1:]), search_px=RP["search_px"], ncc_window=RP["ncc_window"],
                               opening_factor=RO["factor"], relief_height_m=RO["relief_height_m"], cell_m=M.CELL, min_views=RC["min_views"],
                               removal_share=RR["share"], growth_ring_m=RG["ring_m"], growth_step_m=RG["step_m"], growth_dz_m=RG["dz_m"],
                               size_min_extent_m=RS["min_extent_m"], size_min_area_m2=RS["min_area_m2"], size_min_height_m=RS["min_height_m"],
                               max_view_angle_deg=M.RULE["pairs"]["max_view_angle_deg"], target_overlap=M.RULE["pairs"]["target_overlap"],
                               steep_not_judged_nz_below=M.STEEP_NZ, height_difference="non-steep prior pixels only (2.5-D top surface)",
                               growth_piece_min_m2=M.PIECE_MIN_M2, size_extent="minimum-area rotated rectangle",
                               size_stage="after the growth"),
              areas_m2=dict(vote=round(rec0["vote_cells"] * A, 2), removal_added=round(rec0["removal_added_cells"] * A, 2),
                            grown=round(rec0["growth_added_cells"] * A, 2), final=round(rec0["final_cells"] * A, 2)),
              inputs=dict(export=str(M.ex_dir(site, prior)), images=str(M.S0 / "fork_inputs/s61" / site / "images"), pairs=det["pairs_file"],
                          regions=str(M.S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")),
              code_test_first_views=a.views or None, seconds=times, smoke=a.result.endswith("_smoke"), scientific_verdict=None)
    M.jdump(RD / "receipt.json", rc)
    c25 = rec0["counts"]
    M.log(json.dumps(dict(result=a.result, final_m2=round(rec0["final_cells"] * A, 1), caught=c25["caught"]["11+12"], false=c25["false"]["2+3+4"],
                          filled=rec0["records"]["mvs_filled"]["area_eval_m2"], s=times)))
    return dict(vote_m2=rc["areas_m2"]["vote"], grown_m2=rc["areas_m2"]["grown"], final_m2=rc["areas_m2"]["final"])


if __name__ == "__main__":
    main()
