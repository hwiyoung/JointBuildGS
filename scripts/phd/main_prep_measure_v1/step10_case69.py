"""PHD-MAIN-PREP-MEASURE-v1 step 10 (jointbuildgs:dev, CPU): case 6 (amount of observation, B0 conditions) and case 9
(registration differences, 80 m tiles of R1 and R4).

  python step10_case69.py case6
  python step10_case69.py case9 <range_id>

case 6: per condition (COVER, A15, A9, A3) and prior, the judgment units of the B0 target building (footprint + 2 m):
        patch states, support votes, propagated judgments, against the true labels (gt_clean); and the patch states of
        every condition rendered in the common evaluation view 0002 (the GeoGS test view of A15 / A9 / A3).
case 9: the tile shifts of step 03 (observation only) as arrows, with the gate NMAD (roof-like height differences, the
        4.1 measure) and, as an extra column, the NMAD of all confidence-1 building-face residuals (roof-like vertical and
        wall normal) inside the tile on the same 20 gate views with the range shift and with the tile shift (fix-4 measure;
        separate random generator, step 03 outputs untouched).
Outputs: step10/case6.json, case6_view0002.png; step10/case9_<range>.json, case9_<range>.png. scientific_verdict: null."""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np
from shapely.geometry import Point, Polygon

from common import CFG, DENSE, OUT, GRID_H, GRID_W, Views, global_to_local, inside_range, jdump, read_depth_bin, xy_to_uv
from src.phd.prior_propagation_v4 import conversion as conv
from src.phd.prior_propagation_v4 import locations as locs
from src.phd.prior_propagation_v4 import rule
import step03_stage1 as s3

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
D = OUT / "step10"
CLS = ["지지·일치", "지지·충돌", "결측→일치", "결측→충돌", "결측→혼재·근거 부족", "비가시", "패치 없음(덮개 등)"]
CCOL = ["#a6dba0", "#f4a582", "#1b7837", "#b2182b", "#f0b429", "#4a6fd1", "#bdbdbd"]


def unit_class(U):
    st, vo, J = U["state"], U["vote"], U["J"]
    c = np.full(len(st), -1, np.int8)
    c[(st == rule.ST_SUPPORT) & (vo == rule.V_AGREE)] = 0
    c[(st == rule.ST_SUPPORT) & (vo == rule.V_CONFLICT)] = 1
    c[(st == rule.ST_MISSING) & (J == rule.J_AGREE)] = 2
    c[(st == rule.ST_MISSING) & (J == rule.J_CONFLICT)] = 3
    c[(st == rule.ST_MISSING) & ((J == rule.J_MIXED) | (J == rule.J_INSUFF))] = 4
    c[st == rule.ST_INVISIBLE] = 5
    return c


def case6():
    D.mkdir(parents=True, exist_ok=True)
    R = json.loads((OUT / "step01/ranges.json").read_text())
    fpoly = Polygon(R["B0BLD"]["polygon_local"]).buffer(2.0)
    V = Views()
    conds = ["COVER", "A15", "A9", "A3"]
    out = {}
    imgs = {}
    view = "DJI_20241217101259_0002_D.JPG"
    for C in conds:
        for prior in ("LoD2", "ALS"):
            S1 = OUT / "step03_b0cond" / C / "B0" / prior
            if not (S1 / "units.npz").exists():
                continue
            U = locs.load_store(S1 / "units.npz")
            summ = json.loads((S1 / "summary.json").read_text())
            L = OUT / "step04_b0cond" / C / "B0" / f"labels_{prior}.npz"
            G = dict(np.load(L)) if L.exists() else None
            cxy = U["loc_center"][:, :2]
            inb = np.array([fpoly.contains(Point(p)) for p in cxy]) if len(cxy) < 400000 else None
            if inb is None:
                from matplotlib.path import Path as MP
                inb = MP(np.asarray(fpoly.exterior.coords)).contains_points(cxy)
            area = U["loc_area"]; k = U["loc_kind"]; st = U["state"]; vo = U["vote"]; J = U["J"]
            A = lambda m: round(float(area[m].sum()), 1)
            rec = dict(views=summ["views"], tau_roof=summ["tolerance"]["roof"]["tau"], tau_wall=summ["tolerance"]["wall"]["tau"],
                       wall_side=summ["tolerance"]["wall"]["side"], shift=summ["registration"]["shift_applied"])
            for kn, kk in (("roof", 1), ("wall", 2)):
                m = inb & (k == kk)
                if not m.any():
                    continue
                tot = float(area[m].sum())
                rec[kn] = dict(area_m2=round(tot, 1),
                               support_share=round(A(m & (st == rule.ST_SUPPORT)) / tot, 4), missing_share=round(A(m & (st == rule.ST_MISSING)) / tot, 4),
                               invisible_share=round(A(m & (st == rule.ST_INVISIBLE)) / tot, 4),
                               support_conflict_share=round(A(m & (st == rule.ST_SUPPORT) & (vo == rule.V_CONFLICT)) / max(A(m & (st == rule.ST_SUPPORT)), 1e-9), 4),
                               missing_judgment={rule.J_NAMES[j]: A(m & (st == rule.ST_MISSING) & (J == j)) for j in rule.J_NAMES},
                               inherit_area_share=round((A(m & (st == rule.ST_INVISIBLE)) + A(m & (st == rule.ST_MISSING) & ((J == rule.J_MIXED) | (J == rule.J_INSUFF)))) / tot, 4))
                if G is not None:
                    lab = G["label"]; ok = m & ~G["excluded"]
                    sup = ok & (st == rule.ST_SUPPORT); mis = ok & (st == rule.ST_MISSING)
                    rec[kn]["vs_true"] = dict(
                        gt_units=int((ok & (lab >= 0)).sum()),
                        support_right=int((sup & (((vo == rule.V_AGREE) & (lab == 0)) | ((vo == rule.V_CONFLICT) & (lab == 1)))).sum()),
                        support_wrong=int((sup & (((vo == rule.V_AGREE) & (lab == 1)) | ((vo == rule.V_CONFLICT) & (lab == 0)))).sum()),
                        propagated_right=int((mis & (((J == rule.J_AGREE) & (lab == 0)) | ((J == rule.J_CONFLICT) & (lab == 1)))).sum()),
                        propagated_wrong=int((mis & (((J == rule.J_AGREE) & (lab == 1)) | ((J == rule.J_CONFLICT) & (lab == 0)))).sum()),
                        inherited_true_agree=int((ok & ((st == rule.ST_INVISIBLE) | ((st == rule.ST_MISSING) & ((J == rule.J_MIXED) | (J == rule.J_INSUFF)))) & (lab == 0)).sum()),
                        inherited_true_conflict=int((ok & ((st == rule.ST_INVISIBLE) | ((st == rule.ST_MISSING) & ((J == rule.J_MIXED) | (J == rule.J_INSUFF)))) & (lab == 1)).sum()))
            out[f"{C}/{prior}"] = rec
            # render the unit classes in the common view
            pr = s3.Prior(OUT / "step02" / "B0", prior)
            pr.shift = np.asarray(summ["registration"]["shift_applied"], float)
            sc, _ = pr.scene()
            Dr = V.rays(view); Cc = V.C(view)
            tP, tri = sc.cast(Cc, Dr)
            hit = tri >= 0
            ci = np.full(tri.shape, -1, np.int64); ci[hit] = pr.ci_of_tri[tri[hit]]
            X = Cc[None, None, :] + tP[..., None] * Dr.astype(np.float64)
            cls = np.full(tri.shape, -1, np.int8)
            okl = ci >= 0
            loc = locs.locate(U, ci[okl], X[okl])
            cu = unit_class(U)
            cls[okl] = cu[loc]
            cls[hit & ~okl] = 6
            imgs[(C, prior)] = cls
    jdump(D / "case6.json", dict(task_id="PHD-MAIN-PREP-MEASURE-v1", case=6, units="B0 target building footprint + 2 m", common_view=view,
                                 conditions=out, scientific_verdict=None))
    # figure
    R0 = json.loads((OUT / "step01/ranges.json").read_text())["B0BLD"]["polygon_local"]
    ring = np.asarray(R0)
    pts = np.concatenate([np.column_stack([ring, np.full(len(ring), zz)]) for zz in (-46.0, -20.0)])   # footprint at ground and roof height
    u, v, z = V.project(view, pts)
    x0, x1 = int(max(0, np.nanmin(u) - 30)), int(min(GRID_W, np.nanmax(u) + 30)); y0, y1 = int(max(0, np.nanmin(v) - 30)), int(min(GRID_H, np.nanmax(v) + 30))
    import cv2
    img = cv2.imread(str(DENSE / "images" / view))[:, :, ::-1]; img = cv2.resize(img, (GRID_W, GRID_H), interpolation=cv2.INTER_AREA)
    fig, axs = plt.subplots(2, 5, figsize=(22, 8.2), constrained_layout=True)
    for r, prior in enumerate(("LoD2", "ALS")):
        axs[r, 0].imshow(img[y0:y1, x0:x1]); axs[r, 0].set_title(f"시점 0002 (평가 영상) — {prior}", fontsize=9)
        for c, C in enumerate(conds):
            ax = axs[r, c + 1]
            cl = imgs.get((C, prior))
            if cl is None:
                ax.axis("off"); continue
            ax.imshow(np.where(cl < 0, 7, cl)[y0:y1, x0:x1], cmap=ListedColormap(CCOL + ["#ffffff"]), vmin=0, vmax=7, interpolation="nearest")
            rec = out[f"{C}/{prior}"]
            ax.set_title(f"{C}: 학습 {rec['views']}장 · τ지붕 {rec['tau_roof']:.2f} m", fontsize=9)
        for ax in axs[r]:
            ax.set_xticks([]); ax.set_yticks([])
    fig.legend(handles=[Patch(color=CCOL[i], label=CLS[i]) for i in range(7)], loc="lower center", ncol=7, fontsize=8.5, bbox_to_anchor=(0.5, -0.04))
    fig.savefig(D / "case6_view0002.png", dpi=85, bbox_inches="tight"); plt.close(fig)
    print("case6", {k: (v["views"], v.get("roof", {}).get("support_share"), v.get("roof", {}).get("invisible_share")) for k, v in out.items()})


def case9(rid):
    D.mkdir(parents=True, exist_ok=True)
    rng = json.loads((OUT / "step01/ranges.json").read_text())[rid]
    views = json.loads((OUT / "step01/views.json").read_text())["views"][rid]["train"]
    gv20 = [views[int(i)] for i in np.unique(np.linspace(0, len(views) - 1, min(20, len(views))).round().astype(int))]
    V = Views(); RG = np.random.default_rng(20261002)
    tm = CFG["registration"]["tile_check"]["tile_m"]
    res = {}
    fig, axs = plt.subplots(1, 2, figsize=(16, 7.5), constrained_layout=True)
    for ai, prior in enumerate(("LoD2", "ALS")):
        S1 = OUT / "step03" / rid / prior
        summ = json.loads((S1 / "summary.json").read_text())
        tiles = summ["registration"].get("tiles", [])
        sh0 = np.asarray(summ["registration"]["shift_applied"], float)
        pr = s3.Prior(OUT / "step02" / rid, prior)
        rows = []
        for t in tiles:
            cx_, cy_ = t["centre_local"]; x0, y0 = cx_ - tm / 2, cy_ - tm / 2
            vals = {}
            for name, sxy in (("range", sh0[:2]), ("tile", np.asarray(t["shift_xy_tile"]))):
                pr.shift = np.array([sxy[0], sxy[1], sh0[2]]); sc, _ = pr.scene()
                pool = []
                for n in gv20:
                    Dr = V.rays(n); Cc = V.C(n)
                    tP, tri = sc.cast(Cc, Dr)
                    dm = read_depth_bin(DENSE / "stereo/depth_maps" / f"{n}.geometric.bin")
                    hit = tri >= 0
                    idx = np.nonzero(hit.ravel())[0]
                    trf = tri.ravel()[idx]
                    d = Dr.reshape(-1, 3)[idx].astype(np.float64)
                    a1 = (np.isfinite(dm) & (dm > 0)).ravel()[idx]
                    X = Cc[None, :] + tP.ravel()[idx][:, None] * d
                    m_ = pr.bface_tri[trf] & a1 & inside_range(X[:, :2], rng) & (X[:, 0] >= x0) & (X[:, 0] < x0 + tm) & (X[:, 1] >= y0) & (X[:, 1] < y0 + tm)
                    k = np.nonzero(m_)[0]
                    if len(k) > 20000:
                        k = RG.choice(k, 20000, replace=False)
                    f_ = conv.factor(pr.n_used[trf[k]], d[k])
                    pool.append((dm.ravel()[idx][k] - tP.ravel()[idx][k]) * f_)
                p = np.concatenate(pool) if pool else np.zeros(0)
                med = np.median(p) if len(p) else np.nan
                vals[name] = float(1.4826 * np.median(np.abs(p - med))) if len(p) else None
            dsh = np.asarray(t["shift_minus_range"])
            rows.append(dict(tile=t["tile"], centre_local=t["centre_local"], fit_pixels=t["fit_pixels"], estimable=t["estimable"],
                             shift_xy_tile=t["shift_xy_tile"], shift_minus_range=t["shift_minus_range"], shift_minus_range_norm_m=float(np.linalg.norm(dsh)),
                             gate_nmad_range_shift=t["nmad_with_range_shift"], gate_nmad_tile_shift=t["nmad_with_tile_shift"],
                             allface_nmad_range_shift=vals["range"], allface_nmad_tile_shift=vals["tile"]))
        res[prior] = dict(range_shift=sh0.tolist(), tiles=rows)
        ax = axs[ai]
        for r in rows:
            cx_, cy_ = r["centre_local"]
            sq = np.array([[cx_ - tm / 2, cy_ - tm / 2], [cx_ + tm / 2, cy_ - tm / 2], [cx_ + tm / 2, cy_ + tm / 2], [cx_ - tm / 2, cy_ + tm / 2], [cx_ - tm / 2, cy_ - tm / 2]])
            q = xy_to_uv(sq); c = xy_to_uv(np.array([[cx_, cy_]]))[0]
            g0, g1 = r["gate_nmad_range_shift"], r["gate_nmad_tile_shift"]
            a0, a1_ = r["allface_nmad_range_shift"], r["allface_nmad_tile_shift"]
            better = (g1 is not None and g0 is not None and g1 < g0) and (a1_ is not None and a0 is not None and a1_ < a0)
            ax.plot(q[:, 0], q[:, 1], color="#555555", lw=0.8)
            dd = xy_to_uv(np.array([[cx_ + r["shift_minus_range"][0], cy_ + r["shift_minus_range"][1]]]))[0] - c
            ax.arrow(c[0], c[1], dd[0] * 30, dd[1] * 30, width=0.8, color="#1a9850" if better else "#d73027", length_includes_head=True)
            ax.text(c[0], c[1] - 6, f"{np.linalg.norm(r['shift_minus_range']):.2f} m\n높이차 NMAD {g0:.3f}→{g1:.3f}\n전체면 NMAD {a0:.3f}→{a1_:.3f}", fontsize=7, ha="center")
        u0, u1 = rng["u_m"]; v0, v1 = rng["v_m"]
        ax.plot([u0, u1, u1, u0, u0], [v0, v0, v1, v1, v0], color="#333333", ls="--", lw=0.8)
        ax.set_aspect("equal"); ax.invert_yaxis(); ax.set_xlabel("u (m)"); ax.set_ylabel("v (m)")
        ax.set_title(f"{rid} {prior}: 구역 이동 − 범위 이동 (화살표 30배; 초록 = 두 NMAD 모두 줄어듦, 빨강 = 아님)", fontsize=9.5)
    fig.savefig(D / f"case9_{rid}.png", dpi=85); plt.close(fig)
    jdump(D / f"case9_{rid}.json", dict(task_id="PHD-MAIN-PREP-MEASURE-v1", case=9, range=rid, gate_views=gv20, result=res, scientific_verdict=None))
    print("case9", rid, {p: [(r["tile"], round(r["shift_minus_range_norm_m"], 3), r["gate_nmad_range_shift"] and round(r["gate_nmad_range_shift"], 3),
                              r["gate_nmad_tile_shift"] and round(r["gate_nmad_tile_shift"], 3), r["allface_nmad_range_shift"] and round(r["allface_nmad_range_shift"], 3),
                              r["allface_nmad_tile_shift"] and round(r["allface_nmad_tile_shift"], 3)) for r in res[p]["tiles"]] for p in res})


def case7(specs):
    """case 7 (mostly changed scene): specs = list of (label, stage1 dir, gt dir) relative to /out; the first is the
    B173-only box. Table: residual record (clipped share), tau, registration, support conflict share, judgments against
    the true labels; figure: roof residual histograms."""
    D.mkdir(parents=True, exist_ok=True)
    res = {}
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.2), constrained_layout=True)
    for label, s1, gt in specs:
        for ai, prior in enumerate(("LoD2", "ALS")):
            S1 = OUT / s1 / prior
            if not (S1 / "summary.json").exists():
                continue
            summ = json.loads((S1 / "summary.json").read_text())
            rs = np.load(S1 / "residual_samples.npz")
            from src.phd.prior_propagation_v4 import tolerance as tol
            fixed = summ.get("fixed")
            if fixed and np.allclose(summ["registration"]["shift_applied"], 0):
                # judgments used the fixed registration (0): residuals = the unshifted roof-like height differences of pass 1
                xh = np.load(S1 / "nk_samples.npz")["vert"].astype(np.float64)      # h_MVS - h_prior (roof-like, confidence 1)
                rr = tol.robust_width(-xh); src = "pass-1 roof-like samples, fixed registration 0"
            else:
                xh = -rs["roof"].astype(np.float64); rr = tol.robust_width(rs["roof"].astype(np.float64)); src = "tolerance samples after the run's registration"
            U = dict(np.load(S1 / "units.npz")); inr = U["loc_in_range"]
            G = dict(np.load(OUT / gt / f"labels_{prior}.npz")) if (OUT / gt / f"labels_{prior}.npz").exists() else None
            st, vo, J = U["state"], U["vote"], U["J"]
            sup = inr & (st == rule.ST_SUPPORT); mis = inr & (st == rule.ST_MISSING)
            rec = dict(views=summ["views"], shift=summ["registration"]["shift_applied"], tau_roof=summ["tolerance"]["roof"]["tau"],
                       tau_wall=summ["tolerance"]["wall"]["tau"], roof_record={k: rr.get(k) for k in ("n", "median_before", "nmad_before", "clipped_share", "median_after", "nmad_after")},
                       support_conflict_share=float(((sup & (vo == rule.V_CONFLICT)).sum()) / max(sup.sum(), 1)),
                       missing_judgment={rule.J_NAMES[j]: int((mis & (J == j)).sum()) for j in rule.J_NAMES})
            if G is not None:
                lab = G["label"]; ok = ~G["excluded"]
                rec["true_conflict_share"] = float(((inr & ok & (lab == 1)).sum()) / max((inr & ok & (lab >= 0)).sum(), 1))
                rec["support_vs_true"] = dict(right=int((sup & ok & (((vo == rule.V_AGREE) & (lab == 0)) | ((vo == rule.V_CONFLICT) & (lab == 1)))).sum()),
                                              wrong=int((sup & ok & (((vo == rule.V_AGREE) & (lab == 1)) | ((vo == rule.V_CONFLICT) & (lab == 0)))).sum()))
                rec["propagated_vs_true"] = dict(right=int((mis & ok & (((J == rule.J_AGREE) & (lab == 0)) | ((J == rule.J_CONFLICT) & (lab == 1)))).sum()),
                                                 wrong=int((mis & ok & (((J == rule.J_AGREE) & (lab == 1)) | ((J == rule.J_CONFLICT) & (lab == 0)))).sum()))
                # the labels with a fixed reference tolerance (the search range R2) for comparison
            res[f"{label}/{prior}"] = rec
            x = xh                           # height MVS - prior on roof-like faces under the registration the judgments used
            rec["residual_source"] = src
            axs[ai].hist(np.clip(x, -8, 8), bins=160, range=(-8, 8), histtype="step", lw=1.4, density=True, label=f"{label} (τ {rec['tau_roof']:.2f} m)")
            axs[ai].set_title(f"{prior}: 지붕 잔차(현재 − 사전 정보 높이, 정합 뒤)", fontsize=9.5); axs[ai].set_xlabel("m"); axs[ai].set_yscale("log")
    for ax in axs:
        ax.legend(fontsize=8)
    fig.savefig(D / "case7_residuals.png", dpi=90); plt.close(fig)
    jdump(D / "case7.json", dict(task_id="PHD-MAIN-PREP-MEASURE-v1", case=7, specs=specs, result=res, scientific_verdict=None))
    print("case7", {k: (round(v["tau_roof"], 3), [round(s, 3) for s in v["shift"]], round(v["support_conflict_share"], 3), v.get("true_conflict_share")) for k, v in res.items()})


if __name__ == "__main__":
    if sys.argv[1] == "case6":
        case6()
    elif sys.argv[1] == "case7":
        case7([tuple(s.split(",")) for s in sys.argv[2:]])
    else:
        case9(sys.argv[2])
