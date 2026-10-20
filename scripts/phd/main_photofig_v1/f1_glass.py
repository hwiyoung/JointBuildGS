"""PHD-MAIN-PHOTOFIG-v1 figure 1: the glass skylight of B173 주변 (항공 LiDAR unit). Where did the image depth land on the glass, and
what did the GT record there? Place, photos and section from the locked config (places.fig1). (jointbuildgs:dev, CPU)

  python f1_glass.py   -> /docs/figures/photo_fig1_glass.png|pdf|json, /docs/tables/fig1_glass.md|json, /pf/proj/fig1_*.npz

Inputs (read only): region file and patch store of the unit; the fill task's case masks; per-view image depth, observation-confidence and
patch maps (S0/s61/export/B173nb_b10/ALS/{mvs,conf,locmap}) and the photometric (mask-off) depth (fork maps 'mvs_photometric', the
depth before the multi-view consistency filter); the GT (S1/v3/box_gt); the drone LiDAR crops of this task (raw frame, shifted by the
GT height alignment for drawing); the registered ALS TIN and LoD2; the current method seed 0 mesh (S0/stage0/b1_ALS/post/mesh_tsdf.ply).
[이 발주에서 냄] scientific_verdict: null"""
import time

import numpy as np
from scipy.spatial import cKDTree

import pf_geo as G
from pf_common import DOCS, PF, S0, S1, SL, cfg, jdump, log, nmad, now, return_class

SITE, PRIOR = "B173nb_b10", "ALS"
FIG = DOCS / "figures"; TAB = DOCS / "tables"


def gt_top(tree, Xg, P, r=0.25, layer=0.5):
    """median z of the GT top layer (within `layer` below the highest GT point) within r in plan of each P."""
    out = np.full(len(P), np.nan)
    lists = tree.query_ball_point(P[:, :2], r=r)
    for i, l in enumerate(lists):
        if len(l) >= 3:
            z = Xg[l, 2]
            out[i] = np.median(z[z >= z.max() - layer])
    return out


def layers(dz, gap=0.5, min_share=0.05):
    s = np.sort(dz)
    cut = np.nonzero(np.diff(s) > gap)[0]
    groups = np.split(s, cut + 1)
    big = [g for g in groups if len(g) >= min_share * len(s)]
    return dict(groups=[dict(n=int(len(g)), z_min=float(g.min()), z_max=float(g.max()), median=float(np.median(g))) for g in groups if len(g) >= 0.01 * len(s)],
                n_layers_ge_5pct=len(big))


def agree_views(n_ref, Xref, uref, vref, train, tol_px=1.0):
    """[근사] views (other than the reference) whose stored image depth agrees with each reference point by the forward-backward
    reprojection error <= 1 px (COLMAP filter_geom_consistency_max_cost); COLMAP's own source-view selection is not reproduced."""
    cnt = np.zeros(len(Xref), np.int32)
    for m in train:
        if m == n_ref:
            continue
        u, v, z = G.project(m, Xref)
        ins = (z > 0) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741)
        if not ins.any():
            continue
        D = G.export(SITE, PRIOR, "mvs", m)
        iu = np.floor(u[ins]).astype(int); iv = np.floor(v[ins]).astype(int)
        d = D[iv, iu]
        ok = np.isfinite(d) & (d > 0)
        if not ok.any():
            continue
        V = G.views(); k = G.vkey(m)
        R = V.rays(k, np.float64)
        Xs = V.C(k) + R[iv[ok], iu[ok]] * d[ok][:, None]
        ub, vb, zb = G.project(n_ref, Xs)
        err = np.hypot(ub - uref[ins][ok], vb - vref[ins][ok])
        good = np.zeros(len(Xref), bool)
        sel = np.nonzero(ins)[0][ok]
        good[sel] = err <= tol_px
        cnt += good
    return cnt


def main():
    t0 = time.time()
    C = cfg(); P = C["places"]["fig1"]
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{SITE}_{PRIOR}.npz")
    U = np.load(S0 / "s61/box" / SITE / PRIOR / "units.npz")
    case = np.array(P["case_patches"], int); bandp = np.array(P["band_patches"], int)
    code = R["code_ext_v3"].astype(int); viol = R["premise_violation"].astype(bool)
    place = np.concatenate([case, bandp])
    xb = P["place_xy_box"]
    num = dict(case_patches=int(len(case)), band_patches=int(len(bandp)), case_area_m2=float(R["area"][case].sum()),
               premise_violation_patches=dict(case=int(viol[case].sum()), band=int(viol[bandp].sum())),
               missing_patches=dict(case=int(np.isin(code[case], [4, 13]).sum()), band=int(np.isin(code[bandp], [4, 13]).sum()),
                                    band_code4=int((code[bandp] == 4).sum()), band_code13=int((code[bandp] == 13).sum())),
               codes_case={int(k): int(v) for k, v in zip(*np.unique(code[case], return_counts=True))})
    # pass share over all training views (patch store sums)
    num["pass_share_store"] = dict(pixels=int(U["pix_sum"][case].sum()), passed=int(U["a1_sum"][case].sum()),
                                   share=float(U["a1_sum"][case].sum() / max(U["pix_sum"][case].sum(), 1)))
    # GT, drone LiDAR, priors
    Xg, multi, _ = G.gt_points(SITE, xb, margin=3.0)
    tree = cKDTree(Xg[:, :2])
    own = G.in_squares(Xg, U, case)
    on = own >= 0
    Vl, Fl = G.prior_mesh(SITE, "LoD2"); Va, Fa = G.prior_mesh(SITE, "ALS")
    zl = G.raycast_top(Vl, Fl, Xg[on, :2]); za = G.raycast_top(Va, Fa, Xg[on, :2])
    gl = Xg[on, 2] - zl
    num["gt_on_glass"] = dict(points=int(on.sum()), per_m2=float(on.sum() / num["case_area_m2"]), multi_return_share=float(multi[on].mean()),
                              minus_lod2=dict(median_m=float(np.nanmedian(gl)), p05=float(np.nanpercentile(gl, 5)), p95=float(np.nanpercentile(gl, 95))),
                              minus_als=dict(median_m=float(np.nanmedian(Xg[on, 2] - za))), layers_vs_lod2=layers(gl[np.isfinite(gl)]))
    gm = R["gt_med"][case].astype(np.float64)
    num["als_minus_gt_median_m"] = float(-np.nanmedian(gm)); num["als_minus_gt_patches"] = int(np.isfinite(gm).sum())
    L = {}
    for src in ("manual", "nadir"):
        z = np.load(PF / "crop" / SITE / f"{src}.npz")
        X = z["xyz"]; m = (X[:, 0] >= xb[0] - 3) & (X[:, 0] <= xb[2] + 3) & (X[:, 1] >= xb[1] - 3) & (X[:, 1] <= xb[3] + 3)
        L[src] = dict(xyz=X[m], rc=return_class(z["return_number"][m], z["number_of_returns"][m]))
    cells = {}
    for src in ("manual", "nadir"):
        o = G.in_squares(L[src]["xyz"], U, case)
        L[src]["on"] = o >= 0
        Xo = L[src]["xyz"][o >= 0]
        k = np.floor(Xo[:, :2] / 0.5).astype(np.int64)
        kk = k[:, 0] * 100000 + k[:, 1]
        cells[src] = {int(a): float(np.median(Xo[kk == a, 2])) for a in np.unique(kk)}
        num[f"{src}_on_glass"] = dict(points=int(len(Xo)), per_m2=float(len(Xo) / num["case_area_m2"]),
                                      multi_return_share=float(np.mean(L[src]["rc"][o >= 0] > 0)) if len(Xo) else None)
    both = sorted(set(cells["manual"]) & set(cells["nadir"]))
    dd = np.array([cells["manual"][k] - cells["nadir"][k] for k in both])
    num["manual_minus_nadir_on_glass"] = dict(cells_0_5m=int(len(both)), median_m=float(np.median(dd)) if len(dd) else None, nmad_m=nmad(dd) if len(dd) else None,
                                               frame="raw (laz - world shift), no height alignment")
    # image depth on the glass over all training views
    train = G.jl(S0 / "fork_inputs/s61" / SITE / "split.json")["train"]
    cs = set(case.tolist())
    dz_all, n_pix, n_pass = [], 0, 0
    sec = P["section"]; c = np.asarray(sec["centre_xy"]); a = np.asarray(sec["axis_xy"]); sr = sec["s_range_m"]
    allp, allf, Xbelow = [], [], []
    for n in train:
        lm = G.export(SITE, PRIOR, "locmap", n)
        msk = np.isin(lm, case)
        if not msk.any():
            continue
        cf = G.export(SITE, PRIOR, "conf", n) > 0.5
        n_pix += int(msk.sum()); n_pass += int((msk & cf).sum())
        X, iy, ix = G.backproject(n, G.export(SITE, PRIOR, "mvs", n), msk & cf)
        if len(X):
            dzx = X[:, 2] - gt_top(tree, Xg, X)
            dz_all.append(dzx)
            Xbelow.append(X[dzx < -0.2])
            b, sb = G.band(X, c, a, sr)
            allp.append(np.column_stack([sb[b], X[b, 2]]))
        Xf, _, _ = G.backproject(n, G.fork_map(SITE, "mvs_photometric", n), msk & ~cf)
        if len(Xf):
            b, sb = G.band(Xf, c, a, sr)
            allf.append(np.column_stack([sb[b], Xf[b, 2]]))
    dz_all = np.concatenate(dz_all) if dz_all else np.zeros(0)
    dz_ok = dz_all[np.isfinite(dz_all)]
    num["image_depth_on_glass_all_views"] = dict(pixels=n_pix, passed=n_pass, pass_share=float(n_pass / max(n_pix, 1)),
                                                 minus_gt_median_m=float(np.median(dz_ok)) if len(dz_ok) else None, minus_gt_nmad_m=nmad(dz_ok) if len(dz_ok) else None,
                                                 n_with_gt=int(len(dz_ok)), share_below_gt_0_2m=float(np.mean(dz_ok < -0.2)) if len(dz_ok) else None,
                                                 share_above_gt_0_2m=float(np.mean(dz_ok > 0.2)) if len(dz_ok) else None)
    # mirror test (candidate 'reflection'): image-depth points more than 0.2 m below the GT top, mirrored through the local GT plane
    # (PCA plane of the GT top layer within 0.5 m, >= 10 points); distance of the mirrored point to the nearest GT point (3-D), and of the
    # point itself (control)
    Xb = np.concatenate(Xbelow) if Xbelow else np.zeros((0, 3))
    tr3 = cKDTree(Xg)
    mir, own_d, mir_d = [], [], []
    lists = tree.query_ball_point(Xb[:, :2], r=0.5) if len(Xb) else []
    for i, l in enumerate(lists):
        if len(l) < 10:
            continue
        Q = Xg[l]; Q = Q[Q[:, 2] >= Q[:, 2].max() - 0.5]
        if len(Q) < 10:
            continue
        p0 = Q.mean(0); w, vv = np.linalg.eigh(np.cov((Q - p0).T)); nn = vv[:, 0] * np.sign(vv[2, 0] or 1)
        Xm = Xb[i] - 2 * ((Xb[i] - p0) @ nn) * nn
        mir.append(Xm)
    if mir:
        Mx = np.array(mir)
        mir_d = tr3.query(Mx)[0]
        own_d = tr3.query(Xb[: len(Mx)])[0] if False else None
    sel = [i for i, l in enumerate(lists) if len(l) >= 10]
    own_d = tr3.query(Xb[sel])[0] if sel else np.zeros(0)
    num["mirror_test"] = dict(points_below_0_2m=int(len(Xb)), mirrored=int(len(mir)),
                              mirrored_to_gt_median_m=float(np.median(mir_d)) if len(mir) else None,
                              mirrored_within_0_3m_share=float(np.mean(np.asarray(mir_d) <= 0.3)) if len(mir) else None,
                              itself_to_gt_median_m=float(np.median(own_d)) if len(own_d) else None,
                              rule="the points more than 0.2 m below the GT top layer, mirrored through the local GT top plane (0.5 m, PCA); the nearest GT point to the mirrored point (3-D) vs to the point itself")
    if mir:
        np.savez_compressed(PF / "proj" / "fig1_mirror.npz", X=Xb[sel], Xm=np.array(mir), mir_d=np.asarray(mir_d), own_d=own_d)
    # the two photos
    out_proj = {}
    for tag, view in (("vertical", P["photo_vertical"]["view"]), ("side", P["photo_side"]["view"])):
        lm = G.export(SITE, PRIOR, "locmap", view)
        msk = np.isin(lm, case)
        cf = G.export(SITE, PRIOR, "conf", view) > 0.5
        Xp, iy, ix = G.backproject(view, G.export(SITE, PRIOR, "mvs", view), msk & cf)
        dz = Xp[:, 2] - gt_top(tree, Xg, Xp)
        ph = G.fork_map(SITE, "mvs_photometric", view)
        Xf, fy, fx = G.backproject(view, ph, msk & ~cf)
        dzf = Xf[:, 2] - gt_top(tree, Xg, Xf) if len(Xf) else np.zeros(0)
        Xpp, py, px = G.backproject(view, ph, msk)   # photometric depth on all glass pixels (for the section, the failed ones)
        u, v, zc = G.project(view, Xp)
        cnt = agree_views(view, Xp, ix + 0.5, iy + 0.5, train) if tag == "vertical" else None
        out_proj[tag] = dict(view=view, X_pass=Xp, iy=iy, ix=ix, dz=dz, X_fail=Xf, fy=fy, fx=fx, dz_fail=dzf, agree=cnt)
        e = dict(view=view, glass_pixels=int(msk.sum()), passed=int((msk & cf).sum()), pass_share=float((msk & cf).sum() / max(msk.sum(), 1)),
                 minus_gt_median_m=float(np.nanmedian(dz)) if np.isfinite(dz).any() else None, minus_gt_nmad_m=nmad(dz[np.isfinite(dz)]) if np.isfinite(dz).any() else None,
                 failed_with_photometric_depth=int(len(Xf)), failed_minus_gt_median_m=float(np.nanmedian(dzf)) if np.isfinite(dzf).any() else None)
        if cnt is not None:
            u_, c_ = np.unique(cnt, return_counts=True)
            e["agreeing_views_approx"] = dict(rule=agree_views.__doc__.strip().replace("\n    ", " "), required_by_colmap=2,
                                              distribution={int(a): int(b) for a, b in zip(u_, c_)}, median=float(np.median(cnt)),
                                              share_ge_2=float(np.mean(cnt >= 2)))
        num[f"photo_{tag}"] = e
        log(tag, e)
    np.savez_compressed(PF / "proj" / "fig1_glass.npz", **{f"{t}_{k}": v for t, d in out_proj.items() for k, v in d.items() if isinstance(v, np.ndarray)})
    # section
    mg, sg = G.band(Xg, c, a, sr)
    mm, sm = G.band(L["manual"]["xyz"], c, a, sr)
    t1 = time.time()
    Vm, Fm, minfo = G.read_ply_mesh_box(S0 / "stage0/b1_ALS/post/mesh_tsdf.ply", xb, margin=5.0)
    log("mesh", minfo, f"{time.time() - t1:.0f}s")
    seg_m = G.cut_vertical(Vm, Fm, c, a, sr); seg_a = G.cut_vertical(Va, Fa, c, a, sr); seg_l = G.cut_vertical(Vl, Fl, c, a, sr)
    sec_pts = {}
    for tag in ("vertical", "side"):
        d = out_proj[tag]
        b1, s1 = G.band(d["X_pass"], c, a, sr); b2, s2 = G.band(d["X_fail"], c, a, sr) if len(d["X_fail"]) else (np.zeros(0, bool), np.zeros(0))
        sec_pts[tag] = dict(pass_s=s1[b1], pass_z=d["X_pass"][b1, 2], fail_s=s2[b2] if len(b2) else np.zeros(0), fail_z=d["X_fail"][b2, 2] if len(b2) else np.zeros(0))
    AP = np.concatenate(allp) if allp else np.zeros((0, 2)); AF = np.concatenate(allf) if allf else np.zeros((0, 2))
    num["section_all_views"] = dict(pass_points=int(len(AP)), fail_points_photometric=int(len(AF)))
    np.savez_compressed(PF / "proj" / "fig1_section.npz", gt_s=sg[mg], gt_z=Xg[mg, 2], man_s=sm[mm], man_z=L["manual"]["xyz"][mm, 2] + G.GT_DZ[SITE],
                        all_pass=AP, all_fail=AF,
                        seg_method=seg_m, seg_als=seg_a, seg_lod2=seg_l, **{f"{t}_{k}": v for t, d in sec_pts.items() for k, v in d.items()})
    num["section"] = dict(gt_points=int(mg.sum()), manual_points=int(mm.sum()), method_segments=int(len(seg_m)), als_segments=int(len(seg_a)), lod2_segments=int(len(seg_l)),
                          mvs_pass=dict((t, int(len(d["pass_s"]))) for t, d in sec_pts.items()), mvs_fail=dict((t, int(len(d["fail_s"]))) for t, d in sec_pts.items()),
                          mesh=minfo)
    num["seconds"] = round(time.time() - t0, 1); num["made"] = now(); num["scientific_verdict"] = None
    jdump(TAB / "fig1_glass.json", num)
    log("done", num["seconds"])


if __name__ == "__main__":
    main()
