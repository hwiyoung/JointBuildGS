"""PHD-MAIN-PHOTOFIG-v1 figure 4: the gentle roof of B173 주변 (항공 LiDAR face 1, the 32,932 rows of fixtest fig 1). Did the result stay
above the prior with the image depth, and is the image-depth offset even over the whole site? (jointbuildgs:dev, CPU)

  python f4_roof.py compute   -> /docs/tables/fig4_roof.json|md, /pf/proj/fig4_*.npz
  python f4_roof.py draw      -> /docs/figures/photo_fig4_roof.png|pdf|json

Values per GT row of the roof: prior / results = the signed GT->mesh distance of the distance files (+ outside = above for roofs; SD/dist,
FT/dist); image depth = z of the image-depth point at the GT point (S1/defs/<site>/rows_ALS.npz 'z_mvs', the region metrics' value)
minus the GT z. On the photo: GT points of the roof visible in the photo (z-buffer among the GT points, 0.25 m), coloured by the value.
30,000-iteration dump: the roof's pixels in the photo (ALS patch map), render depth of seed 0 vs the prior render depth, both lifted to
3-D, height difference binned by the narrowed width (5.61 cm, main reading) and the tolerance (14.70 cm). Map: code-2 roof patches of the
evaluation range (median z_mvs - z_GT of their rows) and the study's bare-ground cells (s04_gt_v7.py:172-175, 0.5 m; median of
z_MVS - z_GT of the GT points in the cell, regions_v3/mvs_at_gt). [이 발주에서 냄] scientific_verdict: null"""
import sys
import time

import numpy as np
from matplotlib.collections import LineCollection

import pf_geo as G
from pf_common import DOCS, FT, PF, S0, S1, S2, SD, cfg, jdump, jl, log, nmad, now, xy_to_uv, uv_to_xy, box

SITE, PRIOR = "B173nb_b10", "ALS"
TAU, WID = 0.1470, 0.0561
RUNS = {"지금 방법 씨앗 0": S0 / "stage0/b1_ALS", "지금 방법 씨앗 1": S0 / "stage0/b2_ALS", "허용 구간 없애기": S2 / "runs/B173nb_b10/abl_band_ALS_s0"}
DIST = {"학습 전 사전 정보": SD / "dist/B173nb_b10_ALS__samepath_ALS.npz", "지금 방법 씨앗 0": SD / "dist/B173nb_b10_ALS__prop_ALS_s0.npz",
        "지금 방법 씨앗 1": SD / "dist/B173nb_b10_ALS__prop_ALS_s1.npz", "허용 구간 없애기": FT / "dist/B173nb_b10_ALS__abl_band_ALS_s0.npz"}
COL = {"지금 방법 씨앗 0": "#ff7f0e", "지금 방법 씨앗 1": "#fdbf6f", "허용 구간 없애기": "#9467bd"}


def stats(x):
    x = np.asarray(x, np.float64); x = x[np.isfinite(x)]
    return dict(n=int(len(x)), median_m=float(np.median(x)) if len(x) else None, nmad_m=nmad(x) if len(x) else None)


def compute():
    t0 = time.time()
    C = cfg(); P = C["places"]["fig4"]
    F = np.load(FT / "prep/figpos_fig1_rows.npz")
    rows = F["rows"]; Xr = F["xyz_gt"].astype(np.float64)
    W = np.load(S1 / "defs" / SITE / "rows_ALS.npz")
    vals = {}
    for k, p in DIST.items():
        d = np.load(p)
        pos = np.searchsorted(d["r_idx"], rows)
        ok = (pos < len(d["r_idx"])) & (d["r_idx"][np.minimum(pos, len(d["r_idx"]) - 1)] == rows)
        v = np.full(len(rows), np.nan)
        v[ok] = d["r_d"][pos[ok]] * np.where(d["r_sign"][pos[ok]] == 0, 1, d["r_sign"][pos[ok]])
        vals[k] = v
    vals["영상 깊이"] = W["z_mvs"][rows].astype(np.float64) - Xr[:, 2]
    patches = np.unique(W["patch"][rows])
    num = dict(rows=int(len(rows)), patches=int(len(patches)), minus_gt={k: stats(v) for k, v in vals.items()},
               dist_files={k: str(v) for k, v in DIST.items()}, image_depth_source="S1/defs/B173nb_b10/rows_ALS.npz z_mvs - GT z")
    # dump: |seed 0 - prior| on the roof's pixels of the photo
    view = P["photo"]["view"]
    lm = G.export(SITE, PRIOR, "locmap", view)
    msk = np.isin(lm, patches)
    pr = G.export(SITE, PRIOR, "prior", view)
    Xp, iy, ix = G.backproject(view, pr, msk)
    dump = {}
    for k, r in RUNS.items():
        d = np.load(r / "model/dump/iteration_30000" / f"{view}_depth.npy").astype(np.float64)
        d[~(np.isfinite(d) & (d > 0))] = np.nan
        X, jy, jx = G.backproject(view, d, msk)
        key_p = iy * 1024 + ix; key_r = jy * 1024 + jx
        both, ia, ib = np.intersect1d(key_p, key_r, return_indices=True)
        dz = X[ib, 2] - Xp[ia, 2]
        a = np.abs(dz)
        dump[k] = dict(pixels=int(len(dz)), within_narrowed=float(np.mean(a <= WID)), between=float(np.mean((a > WID) & (a <= TAU))), beyond_tolerance=float(np.mean(a > TAU)),
                       median_minus_prior_m=float(np.median(dz)))
        np.savez_compressed(PF / "proj" / f"fig4_dump_{k}.npz", key=both, dz=dz)
    num["dump_vs_prior_on_photo"] = dict(view=view, rule="render depth (30,000-iteration dump) vs prior render depth on the roof's pixels, both lifted to 3-D; |z_result - z_prior| bins", runs=dump,
                                         narrowed_m=WID, tolerance_m=TAU)
    # site map: code-2 roof patches and bare ground
    R = np.load(S1 / "regions_v3" / f"regions_ext_v3_{SITE}_{PRIOR}.npz")
    code = R["code_ext_v3"].astype(int); ev = R["in_eval"].astype(bool); kind = R["kind"].astype(int)
    sel_p = np.nonzero(ev & (code == 2) & (kind == 1))[0]
    pr_all = W["patch"]; zm_all = W["z_mvs"]; Xg_all = None
    G_ = np.load(S1 / "defs" / SITE / "gt_classes.npz")
    Xg = G_["xyz_gt_points"]
    dzr = W["z_mvs"].astype(np.float64) - Xg[W["point"]][:, 2]
    order = np.argsort(pr_all, kind="stable")
    ps = pr_all[order]; dv = dzr[order]
    u, st, cn = np.unique(ps, return_index=True, return_counts=True)
    pmed = {int(a): float(np.nanmedian(dv[s:s + c])) for a, s, c in zip(u, st, cn) if c >= 5 and np.isfinite(dv[s:s + c]).any()}
    pm = np.array([pmed.get(int(i), np.nan) for i in sel_p])
    surf = R["surf_ext"].astype(int)[sel_p]
    faces = {}
    for e in np.unique(surf):
        m = (surf == e) & np.isfinite(pm)
        if m.sum() >= 20:
            faces[int(e)] = dict(patches=int(m.sum()), median_m=float(np.median(pm[m])), nmad_m=nmad(pm[m]))
    sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1"); sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1"); sys.path.insert(0, "/repo")
    import s04_gt_v7 as s4
    Dg, A = s4.survey_grids()
    dtm = Dg["dtm"].astype(float); uls = Dg["uls"].astype(float); mvs = Dg["mvs"].astype(float)
    rough = A["uls_zmax"] - A["uls_zmin"]
    umulti = np.where(A["uls_n"] > 0, A["uls_n_multi"] / np.maximum(A["uls_n"], 1), 1.0)
    ground = (A["als_n_c2"] >= 2) & (rough < 0.25) & (Dg["fid"] < 0) & (Dg["veg"] < 0.05) & np.isfinite(uls) & np.isfinite(mvs) & (np.abs(uls - dtm) < 1.0) & (umulti < 0.05)
    grid = s4.Grid(dtm.shape)
    Z = np.load(S1 / "regions_v3" / f"mvs_at_gt_{SITE}.npz")
    gi = Z["gt_points_index"]; zmv = Z["gt_points_z_mvs"]
    Xs = Xg[gi].astype(np.float64)
    from pf_common import in_rect
    inr = in_rect(Xs[:, :2], SITE)
    iy_, ix_, ok_ = grid.idx(Xs[:, 0], Xs[:, 1])
    gmask = ok_ & inr & ground[iy_, ix_] & np.isfinite(zmv)
    key = iy_[gmask] * 100000 + ix_[gmask]
    dzg = zmv[gmask] - Xs[gmask, 2]
    o = np.argsort(key, kind="stable"); key, dzg = key[o], dzg[o]
    uk, st, cn = np.unique(key, return_index=True, return_counts=True)
    gmed = np.array([np.median(dzg[s:s + c]) for s, c in zip(st, cn)])
    gxy = np.column_stack([grid.e0 + ((uk % 100000) + 0.5) * grid.res - 690953.0, grid.n0 + ((uk // 100000) + 0.5) * grid.res - 5336071.0])
    num["site_map"] = dict(roof_patches=int(np.isfinite(pm).sum()), roof_median_m=float(np.nanmedian(pm)), roof_nmad_m=nmad(pm[np.isfinite(pm)]),
                           faces=faces, ground_cells=int(len(uk)), ground_points=int(gmask.sum()), ground_median_m=float(np.median(gmed)) if len(gmed) else None,
                           ground_nmad_m=nmad(gmed) if len(gmed) else None, ground_rule="s04_gt_v7.py:172-175 bare-ground cells (0.5 m) in the evaluation range")
    np.savez_compressed(PF / "proj/fig4_map.npz", patch_xy=R["centre"][sel_p][:, :2].astype(np.float64), patch_val=pm, ground_xy=gxy, ground_val=gmed)
    np.savez_compressed(PF / "proj/fig4_rows.npz", xyz=Xr, **{f"v_{i}": v for i, v in enumerate(vals.values())}, names=np.array(list(vals.keys())))
    # section
    sec = P["section"]; c = np.asarray(sec["centre_xy"]); a = np.asarray(sec["axis_xy"]); sr = sec["s_range_m"]
    xb = P["place_xy_box"]
    Xb, _, _ = G.gt_points(SITE, xb, margin=3.0)
    mg, sg = G.band(Xb, c, a, sr)
    Va, Fa = G.prior_mesh(SITE, "ALS")
    segs = {}
    for k, r in RUNS.items():
        V, F_, info = G.read_ply_mesh_box(r / "post/mesh_tsdf.ply", xb, margin=5.0)
        segs[k] = G.cut_vertical(V, F_, c, a, sr); log("mesh", k, info)
    train = G.jl(S0 / "fork_inputs/s61" / SITE / "split.json")["train"]
    AP, AF = [], []
    for n in train:
        lmn = G.export(SITE, PRIOR, "locmap", n)
        mk = np.isin(lmn, patches)
        if not mk.any():
            continue
        cf = G.export(SITE, PRIOR, "conf", n) > 0.5
        X, _, _ = G.backproject(n, G.export(SITE, PRIOR, "mvs", n), mk & cf)
        b, s = G.band(X, c, a, sr); AP.append(np.column_stack([s[b], X[b, 2]]))
        Xf, _, _ = G.backproject(n, G.fork_map(SITE, "mvs_photometric", n), mk & ~cf)
        if len(Xf):
            b, s = G.band(Xf, c, a, sr); AF.append(np.column_stack([s[b], Xf[b, 2]]))
    AP = np.concatenate(AP) if AP else np.zeros((0, 2)); AF = np.concatenate(AF) if AF else np.zeros((0, 2))
    np.savez_compressed(PF / "proj/fig4_section.npz", gt_s=sg[mg], gt_z=Xb[mg, 2], seg_als=G.cut_vertical(Va, Fa, c, a, sr), all_pass=AP, all_fail=AF,
                        **{f"seg_{i}": v for i, v in enumerate(segs.values())}, seg_names=np.array(list(segs.keys())))
    num["section"] = dict(gt_points=int(mg.sum()), mvs_pass=int(len(AP)), mvs_fail=int(len(AF)), segments={k: int(len(v)) for k, v in segs.items()})
    num["copied"] = dict(bias_cm={"지금 방법": 6.2, "학습 전 사전 정보": -1.4, "source": "새 거리 지표(DIST71) 두 자료가 모두 맞는 곳의 치우침"},
                         stage2_fine_ruler_cm={"지금 방법": 6.88, "허용 구간 없애기": 2.55, "source": "2단계 보고서(허용 구간 없애기)"},
                         r2_residual_median_cm={"value": -6.2, "source": "고친 판 시험 준비 보고 2.3 (사전 정보 − 영상 깊이, 탐색 지역 R2)"})
    num["seconds"] = round(time.time() - t0, 1); num["made"] = now(); num["scientific_verdict"] = None
    jdump(DOCS / "tables/fig4_roof.json", num)
    log("done", num["seconds"])


def draw():
    plt = G.setup_plt()
    from matplotlib.colors import Normalize
    C = cfg(); P = C["places"]["fig4"]; N = jl(DOCS / "tables/fig4_roof.json")
    view = P["photo"]["view"]
    Rr = np.load(PF / "proj/fig4_rows.npz")
    X = Rr["xyz"]; names = list(Rr["names"])
    vals = {n: Rr[f"v_{i}"] for i, n in enumerate(names)}
    u, v, z = G.project(view, X)
    x0, x1 = int(max(u.min() - 25, 0)), int(min(u.max() + 25, 1024)); y0, y1 = int(max(v.min() - 25, 0)), int(min(v.max() + 25, 741))
    im = G.image(SITE, view)[y0:y1, x0:x1]
    from PIL import Image
    (DOCS / "figures/crops").mkdir(exist_ok=True)
    Image.fromarray(im).save(DOCS / "figures/crops" / f"photo_fig4_{view}_{x0}_{y0}_{x1}_{y1}.png")
    vis, _, _, _ = G.zbuffer_visible(view, X, tol=0.25)
    lo, hi = C["colour_ranges"]["fig4_minus_gt_m"]
    H_, W_ = im.shape[:2]
    rot = H_ > W_                                           # the roof is long in the image's vertical direction: shown turned 90 deg
    imr = np.rot90(im) if rot else im
    def rxy(uu, vv):                                        # pixel (x, y) in the crop -> shown (x, y) after np.rot90 (counter-clockwise)
        return (vv, (W_ - 1) - uu) if rot else (uu, vv)
    fig = plt.figure(figsize=(15, 21))
    gs = fig.add_gridspec(5, 1, height_ratios=[0.42, 0.42, 0.42, 0.95, 1.2], hspace=0.16)
    panel = [("학습 전 사전 정보", "(가) 사전 정보 − 참값"), ("영상 깊이", "(나) 영상 깊이 − 참값"), ("지금 방법 씨앗 0", "(다) 지금 방법 씨앗 0 − 참값")]
    axes_ph = []
    for j, (k, lab) in enumerate(panel):
        ax = fig.add_subplot(gs[j, 0]); axes_ph.append(ax)
        ax.imshow(imr, interpolation="nearest", alpha=0.85)
        m = vis & np.isfinite(vals[k])
        px, py = rxy(u[m] - x0, v[m] - y0)
        h = ax.scatter(px, py, c=vals[k][m], s=1.0, cmap="RdBu_r", vmin=lo, vmax=hi, linewidths=0)
        st = N["minus_gt"][k]
        ax.text(0.02, 0.98, f"{lab}\n중앙값 {st['median_m']*100:+.1f} cm, NMAD {st['nmad_m']*100:.1f} cm", transform=ax.transAxes, va="top", fontsize=9,
                bbox=dict(fc="w", ec="none", alpha=0.85))
        ax.set_xticks([]); ax.set_yticks([])
    cb = fig.colorbar(h, ax=axes_ph, shrink=0.8, pad=0.01, extend="both"); cb.set_label("− 참값 (m)\n빨강 = 참값보다 위")
    # section
    ax = fig.add_subplot(gs[3, 0])
    S = np.load(PF / "proj/fig4_section.npz")
    sec = P["section"]
    sa = S["seg_als"]
    if len(sa):
        pts = sa.reshape(-1, 2); o = np.argsort(pts[:, 0]); ps, pz = pts[o, 0], pts[o, 1]
        xs = np.linspace(*sec["s_range_m"], 600); zp = np.interp(xs, ps, pz)
        ax.fill_between(xs, zp - TAU, zp + TAU, color="#d9d9d9", alpha=0.8, lw=0, zorder=1)
        ax.fill_between(xs, zp - WID, zp + WID, color="#c7e9c0", alpha=0.9, lw=0, zorder=1)
    rng = np.random.default_rng(0)
    AP = S["all_pass"]
    if len(AP):
        k_ = rng.choice(len(AP), size=min(10000, len(AP)), replace=False)
        ax.plot(AP[k_, 0], AP[k_, 1], "o", color="#8c564b", ms=1.0, alpha=0.25, zorder=2)
    AF = S["all_fail"]
    if len(AF):
        k_ = rng.choice(len(AF), size=min(2000, len(AF)), replace=False)
        ax.plot(AF[k_, 0], AF[k_, 1], "o", mfc="none", mec="#8c564b", ms=1.8, alpha=0.4, zorder=2)
    ax.plot(S["gt_s"], S["gt_z"], ".", color="#000000", ms=1.0, zorder=3)
    ax.add_collection(LineCollection(sa, colors="#7f7f7f", linewidths=2.0, zorder=4))
    for i, k in enumerate(S["seg_names"]):
        ls = "--" if k == "지금 방법 씨앗 1" else "-"
        ax.add_collection(LineCollection(S[f"seg_{i}"], colors=COL[str(k)], linewidths=1.6, linestyles=ls, zorder=5))
    zc = np.nanmedian(S["gt_z"])
    ax.set_xlim(*sec["s_range_m"]); ax.set_ylim(zc - 0.45, zc + 0.45)
    ax.set_xlabel("지붕의 긴 축을 따라 (m)"); ax.set_ylabel("높이 (m)")
    for txt, color, fr in (("검정 점: 참값", "#000000", 0.01), ("회색 선: 항공 LiDAR, 회색 띠: 허용 구간 ±14.7 cm, 초록 띠: 좁힌 폭 ±5.6 cm", "#555555", 0.11),
                           ("주황: 지금 방법 씨앗 0 · 옅은 주황 점선: 씨앗 1", "#ff7f0e", 0.56), ("보라: 허용 구간 없애기", "#9467bd", 0.84)):
        ax.text(fr, 0.97, txt, transform=ax.transAxes, color=color, fontsize=8.5, va="top")
    ax.text(0.01, 0.05, f"4-나. 지붕의 긴 축 단면(폭 0.5 m); 갈색 점 = 학습 영상 모두의 영상 깊이(통과 {len(AP):,}점 가운데 1만 점), 빈 점 = 떨어짐", transform=ax.transAxes, fontsize=9,
            bbox=dict(fc="w", ec="none", alpha=0.8))
    # site map: background = the same vertical training photo laid on the survey DSM (0.25 m cells; s04_gt_v7.survey_grids 'uls' - 604 m)
    ax = fig.add_subplot(gs[4, 0])
    M = np.load(PF / "proj/fig4_map.npz")
    b = box(SITE)
    sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1"); sys.path.insert(0, "/repo/scripts/phd/main_stage0_v1"); sys.path.insert(0, "/repo")
    import s04_gt_v7 as s4
    Dg, _ = s4.survey_grids(); grid = s4.Grid(Dg["dtm"].shape)
    cu = np.arange(b["eval_u"][0], b["eval_u"][1], 0.25) + 0.125; cv = np.arange(b["eval_v"][0], b["eval_v"][1], 0.25) + 0.125
    UU, VV = np.meshgrid(cu, cv)
    xy = uv_to_xy(np.column_stack([UU.ravel(), VV.ravel()]))
    iy_, ix_, ok_ = grid.idx(xy[:, 0], xy[:, 1])
    zz = Dg["uls"][iy_, ix_].astype(float) - 604.0
    pu, pv, pz = G.project(view, np.column_stack([xy, zz]))
    ins = ok_ & np.isfinite(zz) & (pz > 0) & (pu >= 0) & (pu < 1024) & (pv >= 0) & (pv < 741)
    full = G.image(SITE, view)
    ortho = np.ones((len(xy), 3), np.float64)
    ortho[ins] = full[np.floor(pv[ins]).astype(int), np.floor(pu[ins]).astype(int)] / 255.0
    ax.imshow(ortho.reshape(len(cv), len(cu), 3), extent=(cu[0] - 0.125, cu[-1] + 0.125, cv[-1] + 0.125, cv[0] - 0.125), interpolation="nearest", alpha=0.75)
    puv = xy_to_uv(M["patch_xy"]); guv = xy_to_uv(M["ground_xy"])
    ax.scatter(guv[:, 0], guv[:, 1], c=M["ground_val"], s=3, marker="s", cmap="RdBu_r", vmin=lo, vmax=hi, linewidths=0)
    ok = np.isfinite(M["patch_val"])
    ax.scatter(puv[ok, 0], puv[ok, 1], c=M["patch_val"][ok], s=3, marker="s", cmap="RdBu_r", vmin=lo, vmax=hi, linewidths=0)
    ax.plot([b["eval_u"][0], b["eval_u"][1], b["eval_u"][1], b["eval_u"][0], b["eval_u"][0]], [b["eval_v"][0], b["eval_v"][0], b["eval_v"][1], b["eval_v"][1], b["eval_v"][0]], color="0.3", lw=1)
    cuv = xy_to_uv(np.atleast_2d(P["centre"][:2]))
    ax.plot(cuv[:, 0], cuv[:, 1], "*", color="k", ms=12)
    ax.set_aspect("equal"); ax.set_xlim(b["eval_u"][0] - 1, b["eval_u"][1] + 1); ax.set_ylim(b["eval_v"][1] + 1, b["eval_v"][0] - 1)
    ax.set_xlabel("u (m, 상자 축)"); ax.set_ylabel("v (m)")
    sm = N["site_map"]
    ax.text(0.01, 0.02, f"4-다. 평가 범위의 영상 깊이 − 참값: 두 자료가 모두 맞는 지붕 패치 {sm['roof_patches']:,} (중앙값 {sm['roof_median_m']*100:+.1f} cm) · 맨땅 칸 {sm['ground_cells']:,} (중앙값 {sm['ground_median_m']*100:+.1f} cm) · 별 = 그림의 지붕",
            transform=ax.transAxes, fontsize=9, bbox=dict(fc="w", ec="none", alpha=0.85))
    G.locator(fig, SITE, np.asarray(P["centre"][:2]), rect=(0.87, 0.93, 0.09, 0.05))
    d0 = N["dump_vs_prior_on_photo"]["runs"]["지금 방법 씨앗 0"]
    mg = N["minus_gt"]
    line = (f"지붕 참값 행 {N['rows']:,} · − 참값 중앙값(NMAD): 사전 정보 {mg['학습 전 사전 정보']['median_m']*100:+.1f} ({mg['학습 전 사전 정보']['nmad_m']*100:.1f}) cm, 영상 깊이 {mg['영상 깊이']['median_m']*100:+.1f} ({mg['영상 깊이']['nmad_m']*100:.1f}), "
            f"지금 방법 씨앗 0 {mg['지금 방법 씨앗 0']['median_m']*100:+.1f} ({mg['지금 방법 씨앗 0']['nmad_m']*100:.1f}), 씨앗 1 {mg['지금 방법 씨앗 1']['median_m']*100:+.1f}, 허용 구간 없애기 {mg['허용 구간 없애기']['median_m']*100:+.1f} cm · "
            f"덤프의 |지금 방법 − 사전 정보|: 좁힌 폭 안 {d0['within_narrowed']*100:.0f} %, 사이 {d0['between']*100:.0f} %, 허용 오차 밖 {d0['beyond_tolerance']*100:.0f} % ({d0['pixels']:,} 화소)")
    fig.suptitle("결과가 영상 깊이를 따라 사전 정보보다 위에 머물렀는가, 영상 깊이의 치우침은 지역 전체에 고른가", fontsize=14, y=0.995)   # 발주 5.3의 문장 그대로
    fig.text(0.01, 0.004, line, fontsize=8.5)
    for ext in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"photo_fig4_roof.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    jdump(DOCS / "figures/photo_fig4_roof.json", dict(crop=dict(view=view, box_px=[x0, y0, x1, y1]), numbers_line=line, numbers=N, visible_gt_points=int(vis.sum()),
                                                      caption="사진 띠는 90° 돌려 보임(왼쪽 = 영상 위쪽). 4-가: 같은 연직 영상 위, 사진에서 보이는 지붕 참값 점마다 (가) 사전 정보, (나) 영상 깊이, (다) 지금 방법 씨앗 0의 참값과의 차(±15 cm). 4-나: 지붕의 긴 축 단면. 4-다: 평가 범위를 위에서 본 지도(두 자료가 모두 맞는 지붕 패치와 맨땅 칸의 영상 깊이 − 참값; 바탕 = 같은 연직 영상을 지표 높이(측량 격자 드론 LiDAR 표면)에 편 것, 영상 밖은 흰색).",
                                                      made=now(), scientific_verdict=None))
    print(line)


if __name__ == "__main__":
    {"compute": compute, "draw": draw}[sys.argv[1]]()
