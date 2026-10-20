"""PHD-MAIN-PHOTOFIG-v1 figure 5: B0 항공 LiDAR. Did 폭 좁히기 pull the result towards the right prior where the image is wrong, and is
the difference larger than the scatter of the same setting? (jointbuildgs:dev, CPU)

  python f5_b0.py   -> /docs/figures/photo_fig5_b0.png|pdf|json, /docs/tables/fig5_b0.md|json
Place = the locked cluster of image-error patches (places.fig5). Values per GT row of the cluster = the signed GT->result distance of the
distance files (dist71 rows r_*). Recall at the tolerance = share of rows with |d| <= 12.66 cm. [이 발주에서 냄] scientific_verdict: null"""
import time

import numpy as np
from matplotlib.collections import LineCollection

import pf_geo as G
from pf_common import DOCS, FT, PF, S0, S1, SD, cfg, jdump, log, nmad, now

SITE, PRIOR = "B0_b10", "ALS"
TAU, WID = 0.1266, 0.0808
RES = {"지금 방법 씨앗 0": (S1 / "stage1/B0_b10/prop_ALS_s0", SD / "dist/B0_b10_ALS__prop_ALS_s0.npz"),
       "지금 방법 씨앗 1": (S1 / "stage1/B0_b10/prop_ALS_s1", SD / "dist/B0_b10_ALS__prop_ALS_s1.npz"),
       "지금 방법 다시 돌림": (FT / "runs/B0_b10/fixA_ALS_s0", FT / "dist/B0_b10_ALS__fixA_ALS_s0.npz"),
       "폭 좁히기(기록 셈)": (FT / "runs/B0_b10/fixAT_ALS_s0", FT / "dist/B0_b10_ALS__fixAT_ALS_s0.npz")}
COL = {"지금 방법 씨앗 0": "#ff7f0e", "지금 방법 씨앗 1": "#fdbf6f", "지금 방법 다시 돌림": "#c7c7c7", "폭 좁히기(기록 셈)": "#2ca02c"}


def main():
    t0 = time.time()
    C = cfg(); P = C["places"]["fig5"]
    mem = np.array(P["cluster_patches"], int)
    rows = np.load(S1 / "defs" / SITE / f"rows_{PRIOR}.npz")
    Gc = np.load(S1 / "defs" / SITE / "gt_classes.npz")
    XS = {0: Gc["xyz_gt_points"].astype(np.float64), 1: Gc["xyz_gt_primary"].astype(np.float64)}
    per, ptsv = {}, {}
    ref_idx = None
    for k, (run, df) in RES.items():
        d = np.load(df)
        m = np.isin(d["r_patch"], mem)
        sd = d["r_d"][m].astype(np.float64) * np.where(d["r_sign"][m] == 0, 1, d["r_sign"][m])
        idx = d["r_idx"][m]
        if ref_idx is None:
            ref_idx = idx
        per[k] = dict(rows=int(m.sum()), dist_median_abs_m=float(np.median(np.abs(sd))), signed_median_m=float(np.median(sd)), nmad_m=nmad(sd),
                      recall_tau=float(np.mean(np.abs(sd) <= TAU)), recall_0_2=float(np.mean(np.abs(sd) <= 0.2)))
        ptsv[k] = (idx, sd)
        log(k, per[k])
    src = rows["src"][ref_idx]; pt = rows["point"][ref_idx]
    X = np.zeros((len(ref_idx), 3))
    for s_, A in XS.items():
        mm = src == s_
        X[mm] = A[pt[mm]]
    view = P["photo"]["view"]
    u, v, z = G.project(view, X)
    vis, _, _, _ = G.zbuffer_visible(view, X, tol=0.25)
    x0, x1 = int(max(u.min() - 40, 0)), int(min(u.max() + 40, 1024)); y0, y1 = int(max(v.min() - 40, 0)), int(min(v.max() + 40, 741))
    im = G.image(SITE, view)[y0:y1, x0:x1]
    from PIL import Image
    (DOCS / "figures/crops").mkdir(exist_ok=True)
    Image.fromarray(im).save(DOCS / "figures/crops" / f"photo_fig5_{view}_{x0}_{y0}_{x1}_{y1}.png")
    U = np.load(S0 / "s61/box" / SITE / PRIOR / "units.npz")
    lmc = G.export(SITE, PRIOR, "locmap", view)[y0:y1, x0:x1]
    # section
    sec = P["section"]; c = np.asarray(sec["centre_xy"]); a = np.asarray(sec["axis_xy"]); sr = sec["s_range_m"]
    xb = [c[0] - 8, c[1] - 8, c[0] + 8, c[1] + 8]
    segs = {}
    for k, (run, df) in RES.items():
        V, F, info = G.read_ply_mesh_box(run / "post/mesh_tsdf.ply", xb, margin=3.0)
        segs[k] = G.cut_vertical(V, F, c, a, sr); log("mesh", k, info)
    Va, Fa = G.prior_mesh(SITE, PRIOR)
    seg_a = G.cut_vertical(Va, Fa, c, a, sr)
    Xg = np.concatenate([A[(A[:, 0] >= xb[0]) & (A[:, 0] <= xb[2]) & (A[:, 1] >= xb[1]) & (A[:, 1] <= xb[3])] for A in XS.values()])
    mg, sg = G.band(Xg, c, a, sr)
    near = np.nonzero(np.linalg.norm(U["loc_center"][:, :2] - c, axis=1) <= 7.0)[0]
    train = G.jl(S0 / "fork_inputs/s61" / SITE / "split.json")["train"]
    AP = []
    for n in train:
        l2 = G.export(SITE, PRIOR, "locmap", n)
        mk = np.isin(l2, near)
        if not mk.any():
            continue
        cf = G.export(SITE, PRIOR, "conf", n) > 0.5
        Xm, _, _ = G.backproject(n, G.export(SITE, PRIOR, "mvs", n), mk & cf)
        if len(Xm):
            b_, s_ = G.band(Xm, c, a, sr); AP.append(np.column_stack([s_[b_], Xm[b_, 2]]))
    AP = np.concatenate(AP) if AP else np.zeros((0, 2))
    # draw
    plt = G.setup_plt()
    lo, hi = C["colour_ranges"]["fig5_minus_gt_m"]
    fig = plt.figure(figsize=(15, 12.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.85], hspace=0.16, wspace=0.04)
    for col, k in enumerate(("지금 방법 씨앗 0", "폭 좁히기(기록 셈)")):
        ax = fig.add_subplot(gs[0, col])
        ax.imshow(im, interpolation="nearest", alpha=0.85)
        ax.contour(np.isin(lmc, mem).astype(float), levels=[0.5], colors=["#000000"], linewidths=1.0)
        idx, sd = ptsv[k]
        pos = {int(i): j for j, i in enumerate(ref_idx)}
        val = np.full(len(ref_idx), np.nan)
        for i, s_ in zip(idx, sd):
            if int(i) in pos:
                val[pos[int(i)]] = s_
        m = vis & np.isfinite(val)
        h = ax.scatter(u[m] - x0, v[m] - y0, c=val[m], s=6, cmap="RdBu_r", vmin=lo, vmax=hi, linewidths=0)
        q = per[k]
        ax.text(0.02, 0.98, f"{'(가)' if col == 0 else '(나)'} {k} − 참값\n거리 중앙값 {q['dist_median_abs_m']*100:.1f} cm, 허용 오차 안 {q['recall_tau']*100:.1f} % ({q['rows']}행)",
                transform=ax.transAxes, va="top", fontsize=9, bbox=dict(fc="w", ec="none", alpha=0.85))
        ax.set_xticks([]); ax.set_yticks([])
    cb = fig.colorbar(h, ax=fig.axes[:2], shrink=0.8, pad=0.01, extend="both"); cb.set_label("− 참값 (m)\n빨강 = 참값보다 위(바깥)")
    ax = fig.add_subplot(gs[1, :])
    if len(seg_a):
        pts_ = seg_a.reshape(-1, 2); o = np.argsort(pts_[:, 0])
        xs = np.linspace(*sr, 500); zp = np.interp(xs, pts_[o, 0], pts_[o, 1])
        ax.fill_between(xs, zp - TAU, zp + TAU, color="#d9d9d9", alpha=0.8, lw=0, zorder=1)
        ax.fill_between(xs, zp - WID, zp + WID, color="#c7e9c0", alpha=0.9, lw=0, zorder=1)
    if len(AP):
        ax.plot(AP[:, 0], AP[:, 1], "o", color="#8c564b", ms=1.4, alpha=0.3, zorder=2)
    ax.plot(sg[mg], Xg[mg, 2], ".", color="#000000", ms=1.2, zorder=3)
    ax.add_collection(LineCollection(seg_a, colors="#7f7f7f", linewidths=2.0, zorder=4))
    for k, sgm in segs.items():
        ax.add_collection(LineCollection(sgm, colors=COL[k], linewidths=1.6, linestyles="--" if k in ("지금 방법 씨앗 1", "지금 방법 다시 돌림") else "-", zorder=5))
    zc = np.nanmedian(Xg[mg, 2]) if mg.any() else 0
    ax.set_xlim(*sr); ax.set_ylim(zc - 1.2, zc + 1.2)
    ax.set_xlabel("덩어리의 긴 축을 따라 (m)"); ax.set_ylabel("높이 (m)")
    txt = [("검정 점: 참값", "#000000"), ("회색 선: 항공 LiDAR, 회색 띠: 허용 구간 ±12.7 cm, 초록 띠: 좁힌 폭 ±8.1 cm", "#555555"), ("갈색 점: 영상 깊이", "#8c564b")]
    for i, (t, col_) in enumerate(txt):
        ax.text([0.01, 0.12, 0.01][i], [0.97, 0.97, 0.83][i], t, transform=ax.transAxes, color=col_, fontsize=8.5, va="top",
                bbox=dict(fc="w", ec="none", alpha=0.7, pad=1))
    ax.text(0.01, 0.9, "주황: 지금 방법 씨앗 0 · 옅은 주황 점선: 씨앗 1 · 옅은 회색 점선: 지금 방법 다시 돌림 · 초록: 폭 좁히기(기록 셈)", transform=ax.transAxes, fontsize=8.5, va="top")
    ax.text(0.01, 0.05, "(다) 덩어리 가운데를 긴 축으로 지나는 12 m × 0.5 m 단면", transform=ax.transAxes, fontsize=9, bbox=dict(fc="w", ec="none", alpha=0.8))
    G.locator(fig, SITE, c, rect=(0.86, 0.92, 0.1, 0.06))
    line = (f"덩어리 {P['cluster_area_m2']:.2f} m², 패치 {len(mem)}, 참값 행 {per['지금 방법 씨앗 0']['rows']} · 거리 중앙값 / 허용 오차 안: " +
            " · ".join(f"{k} {q['dist_median_abs_m']*100:.1f} cm / {q['recall_tau']*100:.1f} %" for k, q in per.items()) +
            " · 옮긴 값(영상이 틀린 곳 전체, 1,755점): 거리 9.25 → 8.16 cm, 허용 오차 안 74.96 → 78.58 %")
    fig.suptitle("폭 좁히기가 영상이 틀린 곳에서 결과를 맞는 사전 정보 쪽으로 당겼는가, 그 차는 같은 설정의 흔들림보다 큰가", fontsize=13.5, y=0.995)
    fig.text(0.01, 0.004, line, fontsize=8.5, wrap=True)
    for ext in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"photo_fig5_b0.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    out = dict(cluster_patches=int(len(mem)), cluster_area_m2=P["cluster_area_m2"], cluster_gt_points=P["cluster_gt_points"], fallback=P.get("fallback"), results=per,
               photo=view, crop_px=[x0, y0, x1, y1], visible_rows=int(vis.sum()), section=dict(gt=int(mg.sum()), mvs=int(len(AP)), segments={k: int(len(v_)) for k, v_ in segs.items()}),
               copied=dict(source="고친 판 시험 중간 보고", image_error_dist_cm=[9.25, 8.16], image_error_recall_tau_pct=[74.96, 78.58], rows=1755, both_right_dist_cm=[2.57, 2.47], both_right_rows=137426),
               numbers_line=line, seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "tables/fig5_b0.json", out)
    jdump(DOCS / "figures/photo_fig5_b0.json", dict(numbers_line=line, crop=dict(view=view, box_px=[x0, y0, x1, y1]), made=now(), scientific_verdict=None))
    L = ["# 그림 5 숫자: B0 · 항공 LiDAR, 영상이 틀린 곳의 덩어리 [이 발주에서 냄]", "",
         f"- 덩어리: 패치 {len(mem)}, {P['cluster_area_m2']:.2f} m², 참값 점 {P['cluster_gt_points']} (영역 파일). 참값 한 층 덩어리가 없어 여러 층 몫이 가장 작은 덩어리(여러 층 표시 {P.get('cluster_gt_suspect')} / {len(mem)}패치)",
         "", "| 결과 | 참값 행 | 거리 중앙값 (cm) | 부호 있는 중앙값 (cm) | NMAD (cm) | 허용 오차(12.66 cm) 안 | 0.2 m 안 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for k, q in per.items():
        L.append(f"| {k} | {q['rows']} | {q['dist_median_abs_m']*100:.2f} | {q['signed_median_m']*100:+.2f} | {q['nmad_m']*100:.2f} | {q['recall_tau']*100:.1f} % | {q['recall_0_2']*100:.1f} % |")
    L += ["", "- 옮긴 값(고친 판 시험 중간 보고): 영상이 틀린 곳의 거리 9.25 cm → 8.16 cm, 재현율(허용 오차) 74.96 % → 78.58 % (1,755점); 두 자료가 모두 맞는 곳의 거리 2.57 cm → 2.47 cm (137,426점)."]
    (DOCS / "tables/fig5_b0.md").write_text("\n".join(L) + "\n")
    log("done", out["seconds"])


if __name__ == "__main__":
    main()
