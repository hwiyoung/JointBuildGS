"""PHD-MAIN-PHOTOFIG-v1 draw figure 1 (the glass skylight) from f1_glass.py's records. (jointbuildgs:dev, CPU)
  python d1_fig1.py -> /docs/figures/photo_fig1_glass.png|pdf|json, /docs/figures/crops/*.png   scientific_verdict: null"""
import numpy as np
from matplotlib.collections import LineCollection

import pf_geo as G
from pf_common import DOCS, PF, S0, cfg, jdump, jl, now

SITE, PRIOR = "B173nb_b10", "ALS"
FIG = DOCS / "figures"


def crop_box(view, idx_points, margin=14):
    u, v, z = G.project(view, idx_points)
    ok = (z > 0) & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741)
    x0 = int(max(np.floor(u[ok].min()) - margin, 0)); x1 = int(min(np.ceil(u[ok].max()) + margin, 1024))
    y0 = int(max(np.floor(v[ok].min()) - margin, 0)); y1 = int(min(np.ceil(v[ok].max()) + margin, 741))
    return x0, y0, x1, y1


def main():
    plt = G.setup_plt()
    import matplotlib
    C = cfg(); P = C["places"]["fig1"]; N = jl(DOCS / "tables/fig1_glass.json")
    U = np.load(S0 / "s61/box" / SITE / PRIOR / "units.npz")
    case = np.array(P["case_patches"]); bandp = np.array(P["band_patches"])
    mis = np.array(C["places"]["fig2"]["missing_patches"])
    pts = U["loc_center"][np.concatenate([case, bandp])].astype(np.float64)
    Z = np.load(PF / "proj/fig1_glass.npz"); S = np.load(PF / "proj/fig1_section.npz")
    matplotlib.rcParams["hatch.color"] = "#000000"; matplotlib.rcParams["hatch.linewidth"] = 1.0
    rot = lambda a: np.rot90(a, k=1)          # the place is long in the image's vertical direction: shown turned 90 deg (left = image top)
    fig = plt.figure(figsize=(14, 17))
    gs = fig.add_gridspec(4, 1, height_ratios=[1.0, 1.0, 1.0, 1.25], hspace=0.16)
    crops = {}
    for row, (tag, view) in enumerate((("vertical", P["photo_vertical"]["view"]), ("side", P["photo_side"]["view"]))):
        x0, y0, x1, y1 = crop_box(view, pts)
        im = G.image(SITE, view)[y0:y1, x0:x1]
        crops[tag] = dict(view=view, box_px=[x0, y0, x1, y1], shown="turned 90 deg counter-clockwise")
        from PIL import Image
        (FIG / "crops").mkdir(exist_ok=True)
        Image.fromarray(im).save(FIG / "crops" / f"photo_fig1_{view}_{x0}_{y0}_{x1}_{y1}.png")
        lm = G.export(SITE, PRIOR, "locmap", view)[y0:y1, x0:x1]
        ax = fig.add_subplot(gs[row, 0])
        ax.imshow(rot(im), interpolation="nearest")
        mc = rot(np.isin(lm, case).astype(float)); mm = rot(np.isin(lm, mis).astype(float))
        ax.contourf(mc, levels=[0.5, 1.5], colors=["#ffffff"], alpha=0.35, hatches=["////"])
        ax.contour(mc, levels=[0.5], colors=["#000000"], linewidths=0.9)
        ax.contourf(mm, levels=[0.5, 1.5], colors=["#1f77b4"], alpha=0.45)
        ax.contour(mm, levels=[0.5], colors=["#1f77b4"], linewidths=2.0)
        ax.set_xticks([]); ax.set_yticks([])
        lab = "(가) 연직 영상" if tag == "vertical" else "(가) 비스듬히 본 영상"
        ang = P["photo_vertical"]["tilt_deg"] if tag == "vertical" else P["photo_side"]["score"]["sight_angle_deg"]
        ax.text(0.02, 0.98, f"{lab}\n{view}\n{'광축 ' if tag == 'vertical' else '유리로 가는 시선 '}{ang:.0f}°", transform=ax.transAxes, va="top", fontsize=9,
                bbox=dict(fc="w", ec="none", alpha=0.85))
        if row == 0:
            ax.text(0.02, 0.02, "빗금: 맞는 자료를 판단할 수 없는 곳(유리)\n파란 테두리: 결측 패치", transform=ax.transAxes, va="bottom", fontsize=9,
                    bbox=dict(fc="w", ec="none", alpha=0.85))
    # (나) image depth - GT on the vertical photo
    x0, y0, x1, y1 = crops["vertical"]["box_px"]
    view = P["photo_vertical"]["view"]
    im = G.image(SITE, view)[y0:y1, x0:x1]
    D = np.full(im.shape[:2], np.nan)
    iy, ix, dz = Z["vertical_iy"], Z["vertical_ix"], Z["vertical_dz"]
    ok = (iy >= y0) & (iy < y1) & (ix >= x0) & (ix < x1)
    D[iy[ok] - y0, ix[ok] - x0] = dz[ok]
    ax = fig.add_subplot(gs[2, 0])
    ax.imshow(rot(im), interpolation="nearest", alpha=0.75)
    lo, hi = C["colour_ranges"]["fig1_b_image_depth_minus_gt_m"]
    h = ax.imshow(rot(D), cmap="RdBu_r", vmin=lo, vmax=hi, interpolation="nearest", alpha=0.95)
    ax.set_xticks([]); ax.set_yticks([])
    pv = N["photo_vertical"]
    ax.text(0.01, 0.98, f"(나) 관측 신뢰도 검사를 통과한 영상 깊이 − 참값(높이 차)\n유리 화소 {pv['glass_pixels']:,} 가운데 통과 {pv['passed']:,}, 중앙값 {pv['minus_gt_median_m']*100:+.0f} cm",
            transform=ax.transAxes, va="top", fontsize=10, bbox=dict(fc="w", ec="none", alpha=0.85))
    cb = fig.colorbar(h, ax=ax, shrink=0.8, extend="both", pad=0.01); cb.set_label("영상 깊이 − 참값 (m)\n파랑 = 참값보다 아래")
    # (다) section
    ax = fig.add_subplot(gs[3, 0])
    sec = P["section"]
    ax.add_collection(LineCollection(S["seg_als"], colors="#7f7f7f", linewidths=2.0, zorder=2))
    ax.add_collection(LineCollection(S["seg_lod2"], colors="#404040", linewidths=1.0, linestyles=":", zorder=2))
    ax.add_collection(LineCollection(S["seg_method"], colors="#ff7f0e", linewidths=1.4, zorder=4))
    ax.plot(S["gt_s"], S["gt_z"], ".", color="#000000", ms=1.5, zorder=3)
    if len(S["man_s"]):
        ax.plot(S["man_s"], S["man_z"], ".", color="#595959", ms=1.0, zorder=3)
    AP, AF = S["all_pass"], S["all_fail"]
    ax.plot(AP[:, 0], AP[:, 1], "o", color="#8c564b", ms=2.2, alpha=0.7, zorder=5)
    if len(AF):
        ax.plot(AF[:, 0], AF[:, 1], "o", mfc="none", mec="#8c564b", ms=3.0, zorder=5)
    ax.set_xlim(*sec["s_range_m"])
    zz = np.concatenate([S["gt_z"], AP[:, 1]]) if len(AP) else S["gt_z"]
    ax.set_ylim(np.nanpercentile(zz, 0.5) - 1.0, np.nanpercentile(zz, 99.5) + 0.6)
    ax.set_xlabel("유리를 가로지르는 거리 (m)"); ax.set_ylabel("높이 (m, 작업 좌표)")
    def tag_line(txt, color, frac):
        ax.text(frac, 0.95, txt, transform=ax.transAxes, color=color, fontsize=9, va="top")
    tag_line("검정 점: 참값", "#000000", 0.01); tag_line("회색: 항공 LiDAR", "#7f7f7f", 0.14); tag_line("점선: LoD2", "#404040", 0.28)
    tag_line("주황: 지금 방법 씨앗 0", "#ff7f0e", 0.38); tag_line("갈색 점: 영상 깊이(통과)  빈 점: 떨어짐", "#8c564b", 0.56)
    if not len(S["man_s"]):
        ax.text(0.99, 0.05, "수동 비행 점: 이 자리에 없음", transform=ax.transAxes, ha="right", fontsize=9, color="#595959")
    ax.text(0.01, 0.05, "(다) 유리를 가로지르는 단면(폭 0.5 m), 학습 영상 모두의 영상 깊이", transform=ax.transAxes, fontsize=9, bbox=dict(fc="w", ec="none", alpha=0.8))
    G.locator(fig, SITE, np.asarray(P["section"]["centre_xy"]), rect=(0.86, 0.935, 0.1, 0.05))
    g = N["gt_on_glass"]; ia = N["image_depth_on_glass_all_views"]; av = pv["agreeing_views_approx"]
    line = (f"유리 {N['case_area_m2']:.1f} m² · 맞는 자료를 판단할 수 없는 패치 {N['premise_violation_patches']['case']} · 결측 패치 {N['missing_patches']['band']} (둘레 2 m) · "
            f"검사 통과 {ia['pass_share']*100:.0f} % ({ia['passed']:,}/{ia['pixels']:,} 화소, 학습 영상 모두) · 동의 시점 수(근사) 중앙값 {av['median']:.0f} · "
            f"영상 깊이 − 참값 중앙값 {ia['minus_gt_median_m']*100:+.0f} cm (NMAD {ia['minus_gt_nmad_m']*100:.0f} cm) · 참값 {g['per_m2']:.0f}점/m², 여러 반사 {g['multi_return_share']*100:.2f} %, 한 층 · "
            f"항공 LiDAR − 참값 {N['als_minus_gt_median_m']*100:+.0f} cm")
    fig.suptitle("유리 위의 영상 깊이는 어디에 잡혔고, 참값은 유리의 어디를 담았나", fontsize=14, y=0.995)   # 발주 5.1의 문장 그대로(결과를 본 뒤 고치지 않음)
    fig.text(0.01, 0.006, line, fontsize=8.5, wrap=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"photo_fig1_glass.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    jdump(FIG / "photo_fig1_glass.json", dict(title=fig._suptitle.get_text() if fig._suptitle else None, crops=crops, numbers_line=line, numbers=N,
                                               caption="사진은 90° 돌려 보임(왼쪽 = 영상 위쪽). (가) 학습 영상 둘: 연직 영상과, 유리를 보는 영상 가운데 시선이 가장 기운 영상. 빗금 = 맞는 자료를 판단할 수 없는 곳(사례 영역), 파란 테두리 = 둘레 2 m의 결측 패치. "
                                                       "(나) 연직 영상의 유리 화소 가운데 관측 신뢰도 검사를 통과한 화소의 (영상 깊이 − 참값) 높이 차. (다) 유리를 가로지르는 폭 0.5 m 단면.",
                                               made=now(), scientific_verdict=None))
    print(line)


if __name__ == "__main__":
    main()
