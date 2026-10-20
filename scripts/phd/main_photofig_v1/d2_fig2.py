"""PHD-MAIN-PHOTOFIG-v1 draw figure 2 (missing patches around the glass) and its patch table, from f2_missing.py's records; also the
render-depth cross-check of request 4.11 (the 30,000-iteration render depth of the photo on each patch's pixels vs the TSDF mesh).
(jointbuildgs:dev, CPU)
  python d2_fig2.py -> /docs/figures/photo_fig2_missing.png|pdf|json, /docs/tables/fig2_patches.md   scientific_verdict: null"""
import numpy as np
from matplotlib.collections import LineCollection

import pf_geo as G
from pf_common import DOCS, FT, PF, S0, S1, cfg, jdump, jl, now

SITE, PRIOR = "B173nb_b10", "ALS"
FIG = DOCS / "figures"
RUNS = {"지금 방법 씨앗 0": S0 / "stage0/b1_ALS", "지금 방법 씨앗 1": S0 / "stage0/b2_ALS", "결측 지키기": FT / "runs/B173nb_b10/fixB_ALS_s0"}
COL = {"지금 방법 씨앗 0": "#ff7f0e", "지금 방법 씨앗 1": "#fdbf6f", "결측 지키기": "#1f77b4"}


def main():
    plt = G.setup_plt()
    C = cfg(); P = C["places"]["fig2"]; T = jl(DOCS / "tables/fig2_patches.json")
    U = np.load(S0 / "s61/box" / SITE / PRIOR / "units.npz")
    rows = T["rows"]; glass = [r for r in rows if r["in_glass_place"]]
    mis = np.array([r["patch"] for r in glass])
    view = P["photo"]
    pts = U["loc_center"][mis].astype(np.float64)
    u, v, z = G.project(view, pts)
    x0, x1 = int(max(u.min() - 40, 0)), int(min(u.max() + 40, 1024)); y0, y1 = int(max(v.min() - 40, 0)), int(min(v.max() + 40, 741))
    im = G.image(SITE, view)[y0:y1, x0:x1]
    from PIL import Image
    (FIG / "crops").mkdir(exist_ok=True)
    Image.fromarray(im).save(FIG / "crops" / f"photo_fig2_{view}_{x0}_{y0}_{x1}_{y1}.png")
    lm = G.export(SITE, PRIOR, "locmap", view)[y0:y1, x0:x1]
    # render-depth cross-check on the photo
    rd = {}
    Xg, _, _ = G.gt_points(SITE, C["places"]["fig1"]["place_xy_box"], margin=3.0)
    from scipy.spatial import cKDTree
    tg = cKDTree(Xg[:, :2])
    lmf = G.export(SITE, PRIOR, "locmap", view)
    for k, r in RUNS.items():
        dpt = np.load(r / "model/dump/iteration_30000" / f"{view}_depth.npy").astype(np.float64)
        dpt[~(np.isfinite(dpt) & (dpt > 0))] = np.nan
        X, iy, ix = G.backproject(view, dpt, np.isin(lmf, mis))
        pid = lmf[iy, ix]
        res = {}
        for p in mis:
            m = pid == p
            if m.sum() < 1:
                continue
            l = tg.query_ball_point(U["loc_center"][p][:2], r=0.25)
            zt = np.median(Xg[l, 2][Xg[l, 2] >= Xg[l, 2].max() - 0.5]) if len(l) >= 3 else np.nan
            res[int(p)] = dict(pixels=int(m.sum()), render_minus_gt_m=float(np.median(X[m, 2]) - zt))
        rd[k] = res
    rec = np.load(PF / "proj/fig2_records.npz")
    fig = plt.figure(figsize=(14, 13.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.9], hspace=0.15, wspace=0.04)
    for col, k in enumerate(("지금 방법 씨앗 0", "결측 지키기")):
        ax = fig.add_subplot(gs[0, col])
        ax.imshow(im, interpolation="nearest")
        inn = [r["patch"] for r in glass if r.get(f"dist_{k}", {}).get("within_0_2m", 0) >= 0.5]
        out = [r["patch"] for r in glass if r["patch"] not in inn]
        mi = np.isin(lm, inn).astype(float); mo = np.isin(lm, out).astype(float)
        if mi.any():
            ax.contourf(mi, levels=[0.5, 1.5], colors=[COL[k]], alpha=0.6)
        ax.contour(mo, levels=[0.5], colors=[COL[k]], linewidths=1.6)
        for j, r in enumerate(glass):
            if j % 4 and j != len(glass) - 1:
                continue
            uu, vv, _ = G.project(view, np.atleast_2d(r["centre"]))
            ax.annotate(str(j + 1), (uu[0] - x0, vv[0] - y0), xytext=(0, -14 if j % 8 else 12), textcoords="offset points", fontsize=7, color="w", ha="center",
                        bbox=dict(fc="k", ec="none", alpha=0.55, pad=0.8), arrowprops=dict(arrowstyle="-", color="k", lw=0.5))
        if k == "결측 지키기":
            nw = rec["new_in_photo"]
            if len(nw):
                ok = (nw[:, 0] >= y0) & (nw[:, 0] < y1) & (nw[:, 1] >= x0) & (nw[:, 1] < x1)
                ax.plot(nw[ok, 1] - x0, nw[ok, 0] - y0, "s", ms=2.2, color="#1f77b4", mec="w", mew=0.3)
            ep = rec["extra_planted_xyz"]
            if len(ep):
                uu, vv, zz = G.project(view, ep)
                ok = (uu >= x0) & (uu < x1) & (vv >= y0) & (vv < y1)
                ax.plot(uu[ok] - x0, vv[ok] - y0, "x", ms=7, mew=1.8, color="#1f77b4")
        nin = len(inn)
        lab = "(가) 지금 방법 씨앗 0" if col == 0 else "(나) 결측 지키기"
        extra = "" if col == 0 else "\n네모 점: 새로 켠 화소 · ×: 더 심은 점"
        ax.text(0.02, 0.98, f"{lab}\n결과 면이 참값 0.2 m 안인 결측 패치 {nin} / {len(glass)} (칠함; 테두리 = 밖){extra}", transform=ax.transAxes, va="top", fontsize=9,
                bbox=dict(fc="w", ec="none", alpha=0.85))
        ax.set_xticks([]); ax.set_yticks([])
    ax = fig.add_subplot(gs[1, :])
    S = np.load(PF / "proj/fig2_section.npz")
    sec = P["section"]
    ax.add_collection(LineCollection(S["seg_als"], colors="#7f7f7f", linewidths=2.0, zorder=2))
    order = T["seg_order"]
    for i, k in enumerate(order):
        ls = "--" if k == "지금 방법 씨앗 1" else "-"
        ax.add_collection(LineCollection(S[f"seg_{i}"], colors=COL[k], linewidths=1.5 if k != "지금 방법 씨앗 1" else 1.2, linestyles=ls, zorder=4))
    ax.plot(S["gt_s"], S["gt_z"], ".", color="#000000", ms=1.5, zorder=3)
    AP, AF = S["all_pass"], S["all_fail"]
    if len(AP):
        ax.plot(AP[:, 0], AP[:, 1], "o", color="#8c564b", ms=2.2, alpha=0.7, zorder=5)
    if len(AF):
        ax.plot(AF[:, 0], AF[:, 1], "o", mfc="none", mec="#8c564b", ms=3.0, zorder=5)
    zz = S["gt_z"]
    ylo, yhi = np.nanpercentile(zz, 0.5) - 1.0, np.nanpercentile(zz, 99.5) + 1.5
    for s_ in S["missing_s"]:
        ax.axvspan(s_ - 0.125, s_ + 0.125, ymin=0, ymax=0.04, color="#1f77b4", alpha=0.8)
    ax.set_xlim(*sec["s_range_m"]); ax.set_ylim(ylo, yhi)
    ax.set_xlabel("결측 패치에서 유리 쪽으로 (m)"); ax.set_ylabel("높이 (m, 작업 좌표)")
    for txt, color, fr in (("검정 점: 참값", "#000000", 0.01), ("회색: 항공 LiDAR", "#7f7f7f", 0.13), ("주황: 지금 방법 씨앗 0 · 옅은 주황 점선: 씨앗 1", "#ff7f0e", 0.27),
                           ("파랑: 결측 지키기", "#1f77b4", 0.6), ("갈색 점: 영상 깊이", "#8c564b", 0.75)):
        ax.text(fr, 0.97, txt, transform=ax.transAxes, color=color, fontsize=9, va="top")
    ax.text(0.01, 0.07, "(다) 결측 패치와 유리를 함께 가로지르는 단면(폭 0.5 m). 아래 파란 막대: 단면에 든 결측 패치", transform=ax.transAxes, fontsize=9,
            bbox=dict(fc="w", ec="none", alpha=0.8))
    G.locator(fig, SITE, np.asarray(sec["centre_xy"]), rect=(0.86, 0.92, 0.1, 0.06))
    nin = {k: sum(1 for r in glass if r.get(f"dist_{k}", {}).get("within_0_2m", 0) >= 0.5) for k in RUNS}
    on_g = sum(r["new_depth_pixels_fixB"] for r in glass); pl_g = sum(r["extra_planted_points_fixB"] for r in glass)
    line = (f"유리 둘레 결측 패치 {len(glass)}(사전 정보가 맞는 {sum(1 for r in glass if r['code'] == 4)} · 틀린 {sum(1 for r in glass if r['code'] == 13)}) · 참값 0.2 m 안: 지금 방법 씨앗 0 {nin['지금 방법 씨앗 0']}, 씨앗 1 {nin['지금 방법 씨앗 1']}, 결측 지키기 {nin['결측 지키기']} · "
            f"새로 켠 화소: 이 18패치 {on_g:,} / 단위 전체 {T['new_depth_pixels_total']:,} · 더 심은 점: 이 18패치 {pl_g} / 단위 전체 {T['extra_planted_total']}")
    fig.suptitle("결측 패치 위의 결과 면은 어디서 왔고, 결측 지키기는 무엇을 바꾸었나", fontsize=14, y=0.995)   # 발주 5.2의 문장 그대로
    fig.text(0.01, 0.005, line, fontsize=9)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"photo_fig2_missing.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    jdump(FIG / "photo_fig2_missing.json", dict(crop=dict(view=view, box_px=[x0, y0, x1, y1]), numbers_line=line, within_0_2m=nin, render_depth_check=rd,
                                                caption="(가) 지금 방법 씨앗 0, (나) 결측 지키기: 그림 1의 연직 영상 위에 유리 둘레 결측 패치 18개(번호 = 표의 차례). 칠함 = 결과 면이 참값 0.2 m 안(패치의 참값 행 절반 넘게), 테두리 = 밖. "
                                                        "(나)의 네모 점 = 결측 지키기가 학습 전에 깊이 항을 새로 켠 화소(이 영상), × = 더 심은 점. (다) 결측 패치와 유리를 함께 가로지르는 단면.",
                                                made=now(), scientific_verdict=None))
    # the table
    pix = U["pix_sum"]
    L = ["# 그림 2 패치 표: 유리 채광창 둘레의 결측 패치와 평가 범위의 다른 결측 패치 (B173 주변 · 항공 LiDAR) [이 발주에서 냄]", "",
         "- 거리 = 참값 행에서 결과 메시까지의 부호 있는 거리(바깥 +)의 중앙값(새 거리 지표의 점마다 거리; SD/dist, FT/dist). 0.2 m 안 = 행의 절반 넘게 0.2 m 안.",
         "- 면의 높이 차 = TSDF 메시를 패치 중심과 가장 가까운 유리(사례 영역) 패치 중심에서 위로부터 맞힌 높이의 차(결측 − 유리). 참값의 같은 차를 함께 적는다. 괄호 = 두 중심의 가운데 점에서 양쪽으로 5 cm 떨어진 두 점의 결과 면 높이 차(경계의 끊김; 설정의 '이어짐' = 0.1 m 안).",
         "- 가우시안 = 30,000회 덤프에서 그 패치에 놓인 가우시안 수(사전 정보 출신 · 같은 처음 점에서 둘 이상 남은 것), 그 패치 둘레(0.125 m)의 사전 정보 처음 점 수와 지워진 수.",
         "- 새로 켠 화소 = 결측 지키기가 학습 전에 깊이 항을 새로 켠 화소(학습 영상 모두, 학습 전 계산 r16B − r16d), 몫 = 그 패치를 본 화소(패치 저장소 pix_sum)에 대한 몫.", "",
         "| 차례 | 패치 | 곳 | 평가 범위 | 지금 방법이 빌린 판정 (이웃 다섯의 곳) | 결측 지키기 판정 | 참값 행 | 거리 중앙값 씨앗 0 · 씨앗 1 · 결측 지키기 (m) | 면의 높이 차 씨앗 0 · 결측 지키기 · 참값 (m) | 가우시안 씨앗 0 · 결측 지키기 | 사전 정보 처음 점(지워짐) 씨앗 0 · 결측 지키기 | 새로 켠 화소 (몫) | 더 심은 점 |",
         "|---:|---:|---|---|---|---|---:|---|---|---|---|---:|---:|"]
    short = {"맞는 자료를 판단할 수 없는 곳": "판단 불가", "영상이 틀린 곳(문턱 안)": "영상 틀림", "두 자료가 모두 맞는 곳": "둘 다 맞음", "사전 정보가 맞는 결측 패치": "맞는 결측", "사전 정보가 틀린 결측 패치": "틀린 결측",
             "11": "사전 정보 틀림", "12": "둘 다 틀림", "0": "참값 없음"}
    for j, r in enumerate(rows):
        nbp = ", ".join(short.get(x, x) for x in r.get("neighbour_places", []))
        d = " · ".join(f"{r[f'dist_{k}']['median_signed_m']:+.2f}" if f"dist_{k}" in r else "—" for k in RUNS)
        st = (f"{r['surface_지금 방법 씨앗 0']['step_m']:+.2f} · {r['surface_결측 지키기']['step_m']:+.2f} · {r['gt_top_patch_m'] - r['gt_top_neighbour_m']:+.2f}"
              f" (경계 ±5 cm: {r['surface_지금 방법 씨앗 0'].get('boundary_step_m', float('nan')):+.2f} · {r['surface_결측 지키기'].get('boundary_step_m', float('nan')):+.2f})")
        ga = " · ".join(f"{r[f'gauss_{k}']['n']} ({r[f'gauss_{k}']['prior_born']} · {r[f'gauss_{k}']['sharing_initial_point']})" for k in ("지금 방법 씨앗 0", "결측 지키기"))
        pi = " · ".join(f"{r[f'gauss_{k}']['prior_initial_points']} ({r[f'gauss_{k}']['removed']})" for k in ("지금 방법 씨앗 0", "결측 지키기"))
        sh = r["new_depth_pixels_fixB"] / max(int(pix[r["patch"]]), 1)
        L.append(f"| {j + 1 if r['in_glass_place'] else '—'} | {r['patch']} | {short[r['place']]}{'' if r['in_glass_place'] else ' (유리에서 떨어짐)'} | {'안' if r['in_eval'] else '밖'} | "
                 f"{r.get('borrowed_judgment', '—')} ({nbp}) | {r['judgment_fixB']} | {r['gt_rows']} | {d} | {st} | {ga} | {pi} | {r['new_depth_pixels_fixB']} ({sh*100:.0f} %) | {r['extra_planted_points_fixB']} |")
    m = T["mid_report_changed"]
    L += ["", "- '면의 높이 차'가 nan인 줄: 그 패치에서 메시나 참값을 위에서 맞히지 못함(유리에서 떨어진 패치는 가장 가까운 유리 패치가 멀다).",
          f"- 중간 보고의 '읽기가 바뀐 패치'(사전 정보가 맞는 결측 10, 틀린 결측 9, 섞임 6) = 이 표에서 결측 지키기 판정이 바뀐 패치: 사전 정보가 맞는 결측 {m['code4_changed']}(빌린 판정 충돌 10 + 섞임 6, 모두 유리 둘레 차례 1~18 가운데) · 사전 정보가 틀린 결측 {m['code13_changed']}(유리 둘레 1 + 유리에서 떨어진 8). 평가 범위 밖까지 넣으면 바뀐 패치는 {m['changed_any']}개.",
          f"- 평가 범위의 결측 패치는 {len(rows)}개다: 유리 둘레 {len(glass)}(사전 정보가 맞는 {sum(1 for r in glass if r['code'] == 4)}, 틀린 {sum(1 for r in glass if r['code'] == 13)}) + 유리에서 떨어진 사전 정보가 틀린 결측 {len(rows) - len(glass)}. 중간 보고 1절의 '18개뿐'은 유리 둘레만 센 값이다.",
          f"- 렌더 깊이 대조(사진 위의 값, 발주 4.11): `figures/photo_fig2_missing.json` render_depth_check. 패치마다 그 영상 렌더 깊이의 높이 − 참값 맨 위 겹(중앙값)."]
    (DOCS / "tables/fig2_patches.md").write_text("\n".join(L) + "\n")
    print(line)


if __name__ == "__main__":
    main()
