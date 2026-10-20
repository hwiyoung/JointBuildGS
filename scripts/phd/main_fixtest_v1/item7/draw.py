"""PHD-MAIN-FIXTEST-v1 일 7 step 2-3: the redraw of the fill task's unseen_1 (new name unseen_1_v2) and one figure of the cause
(unseen_1_cause), with a numbers json next to each, and the item's raw-number table json (jointbuildgs:dev, CPU; no GPU, no render).
  bash run_item7.sh draw draw.py
Drawing = scripts/phd/main_fill_v1/figs_fl_walls.py draw() (lines 84-165) with two changes:
  * every cell of LoD2 face 53 is drawn, the 3,262 cells outside the unseen set (one training view put a pixel on them) in their own
    colour (sand) with a label; before, they were left transparent and read as white = '없음';
  * the raster is laid on the store's cell grid (cell centres at raster-cell centres), so each square is the cell's own 0.25 m footprint
    (before, the squares sat 0.02 m along s and 0.11 m down in z off the cells; no cell was lost or doubled either way).
Values: the panels' wall-present shares are the fill task's (SL/work/virtual/metrics/B173nb_b10/<result>__LoD2.json 'wall', recomputed
from wall_flags_LoD2.npz by cause.py: the same); the sensitivity values are extra_flags.py's. Reads /item7/cause.json, cause_cells.npz,
view_hits.npz, extra_flags.json. Writes /fig/unseen_1_v2.png/.json, /fig/unseen_1_cause.png/.json, /tab/item7_unseen1.json,
/item7/rule7/*.png (title-less copies for the rule-7 check). scientific_verdict: null."""
import json
import textwrap

import numpy as np
from scipy.ndimage import binary_dilation, binary_fill_holes

import item7_common as I

plt = I.setup_fonts()
DARK, MUTE, WALL_BLUE, EXCL = "#2b2b2b", "#7a7a7a", "#2b5c8a", "#d9d9d9"       # figs_fl_common colours
SAND, SAND_TEXT, SET_GREY = "#ecd29b", "#8a6420", "#6f6f6f"
VIEW = "DJI_20241217101359_0032_D"
FOOT_W = 170
# the rule-7 check (order 11.1 rule 7): written after viewing the title-less copies /item7/rule7/<key>.png of the 10:09 run
RULE7 = {"unseen_1_v2": dict(result="통과", checked="2026-10-20 10:10 KST",
                             note="제목을 가린 판에서 본 방법 칸은 벽이 거의 파랑으로 차고 다른 두 칸은 조각만 있다. 왼쪽 위 모래색 칸에는 "
                                  "'학습 영상 한 장이 본 칸(이 셈에서 뺌)' 글이 붙어 흰 칸(없음)과 헷갈리지 않는다."),
         "unseen_1_cause": dict(result="통과", checked="2026-10-20 10:10 KST",
                                note="제목을 가린 판의 (나)에서 모래색 칸마다 검은 점(그 영상의 화소)이 있고 짙은 회색 칸에는 없다. (가)에서 그 무늬가 "
                                     "왼쪽 위 영역에만 있다.")}


def rgb(h):
    return np.array([int(h[k:k + 2], 16) for k in (1, 3, 5)]) / 255.0


def pct(x, nd=1):
    return "—" if x is None else f"{100 * x:.{nd}f} %"


def tag(ax, x, y, text, color, ha="left", va="center", size=12, weight="bold"):
    """copied from scripts/phd/main_fill_v1/figs_fl_common.py tag (itself figs_bl.tag, lines 373-375)."""
    ax.text(x, y, text, color=color, fontsize=size, fontweight=weight, ha=ha, va=va, zorder=8,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))


def cell_raster(s, z, cell=I.CELL):
    """the drawing raster on the store's cell grid: a cell centre sits at the centre of its raster cell (3-cell margin as wall_grid)."""
    s0 = s.min() - cell / 2 - 3 * cell
    z0 = z.min() - cell / 2 - 3 * cell
    j = np.floor((s - s0) / cell).astype(int)
    i = np.floor((z - z0) / cell).astype(int)
    H, W = i.max() + 4, j.max() + 4
    return i, j, (H, W), (s0, s0 + W * cell, z0, z0 + H * cell)


def save(fig, key, vals, title_artist):
    I.FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(I.FIG / f"{key}.png", dpi=100, bbox_inches="tight", pad_inches=0.15)
    title_artist.set_visible(False)
    (I.OUT / "rule7").mkdir(parents=True, exist_ok=True)
    fig.savefig(I.OUT / "rule7" / f"{key}.png", dpi=60, bbox_inches="tight", pad_inches=0.15)
    title_artist.set_visible(True)
    plt.close(fig)
    vals["rule7"] = dict(RULE7.get(key, {}), how="/item7/rule7/<그림>.png(제목을 가린 판)를 보고 제목 문장을 말할 수 있는지 점검")
    I.jdump(I.FIG / f"{key}.json", vals)
    I.log("figure", key, "|", vals["title"][:100])


def gt_on_wall(w, c0, t, nrm):
    """figs_fl_walls.draw lines 94-98: the GT points within 0.25 m of the wall plane, as (s, z)."""
    G = I.gt_use()
    dg = G - c0
    m = (np.abs(dg @ nrm) <= 0.25) & ((dg @ t) >= w["s_range"][0] - 0.5) & ((dg @ t) <= w["s_range"][1] + 0.5) & \
        (G[:, 2] >= w["z_range"][0] - 0.5) & (G[:, 2] <= w["z_range"][1] + 0.5)
    return np.stack([dg[m] @ t, G[m, 2]], 1)


def draw_v2(w, un, face, C, cause, extra, gpt):
    c0, t, nrm = I.frame(w)
    s, z, in_set, li, Tm = C["s"], C["z"], C["in_set"], C["li"], C["T"]
    li_rule = C["li_rule"]
    pos = {int(l_): k for k, l_ in enumerate(C["loc"])}
    order = np.array([pos[int(p)] for p in un["patch"][face]])
    i, j, shape, ext = cell_raster(s, z)
    occ = np.zeros(shape, bool)
    occ[i, j] = True
    occd = binary_fill_holes(binary_dilation(occ, iterations=2))
    flags = np.load(I.VW / "wall_flags_LoD2.npz")
    VM = (I.jload(I.SL / "tables/virtual_main.json") or {}).get("units", {}).get(f"{I.SITE}/LoD2", {}).get("rows", {})
    g = lambda r, k: ((VM.get(r) or {}).get(k) or {}).get("value")  # noqa: E731
    out_set = ~in_set
    n_li = {v: int((in_set & (li == v)).sum()) for v in (0, 1, 2)}
    fig, axs = plt.subplots(3, 1, figsize=(16, 5.2 * 3 + 1.4), sharex=True)
    fig.subplots_adjust(hspace=0.30, top=0.93, bottom=0.06, left=0.05, right=0.99)
    panels = {}
    for ax, (method, res, label) in zip(axs, I.PANELS):
        fl = np.zeros(len(s), bool)
        fl[order] = flags[res].astype(bool)
        wv = cause["wall_present"]["values"][res]
        img = np.zeros(shape + (4,))
        for m, col in ((in_set & (li != 0), EXCL), (out_set, SAND), (in_set & (li == 0) & ~fl, "#ffffff"), (in_set & (li == 0) & fl, WALL_BLUE)):
            img[i[m], j[m], :3] = rgb(col)
            img[i[m], j[m], 3] = 1.0
        ax.imshow(img, origin="lower", extent=ext, interpolation="nearest", aspect="equal")
        ax.contour(np.linspace(ext[0], ext[1], shape[1]), np.linspace(ext[2], ext[3], shape[0]), occd.astype(float), levels=[0.5],
                   colors=["#8a8a8a"], linewidths=1.0)
        if len(gpt):
            ax.scatter(gpt[:, 0], gpt[:, 1], s=6, c=DARK, lw=0, zorder=4)
        if ax is axs[0]:
            gz = float(np.median(gpt[:, 1]))
            tag(ax, 18.0, gz + 0.5, "지금 지붕 가장자리(참값, 벽면 0.25 m 안)", DARK, ha="center", va="bottom", size=11.5)
            tag(ax, 18.0, w["z_range"][1] + 0.1, "뺀 칸: 지금 지붕보다 위", MUTE, ha="center", va="top", size=10.5, weight="normal")
            tag(ax, -11.5, -40.6, "모래색 칸: 학습 영상 한 장이 본 칸(이 셈에서 뺌)", SAND_TEXT, ha="left", va="center", size=11.5)
            ax.annotate("", xy=(-23.0, -40.6), xytext=(-11.7, -40.6), arrowprops=dict(arrowstyle="-", color=SAND_TEXT, lw=1.2), zorder=7)
        ax.set_xlim(ext[0] - 1, ext[1] + 1)
        ax.set_ylim(ext[2] - 1, ext[3] + 0.5)
        ax.set_ylabel("높이 z (m)")
        ax.tick_params(length=2)
        ax.text(1.0, 1.015, pct(wv["fill_json"]["share"]), transform=ax.transAxes, ha="right", va="bottom", fontsize=24, fontweight="bold", color=DARK)
        ax.text(0.0, 1.02, f"{label} · 벽 있음 · 가상 시점 메시 · 패치 {wv['fill_json']['patches']:,}개", transform=ax.transAxes, ha="left",
                va="bottom", fontsize=12.5, fontweight="bold")
        panels[method] = dict(result=res, share=wv["fill_json"]["share"], present=wv["fill_json"]["present"], patches=wv["fill_json"]["patches"],
                              value_source=wv["fill_json"]["source"], recomputed_from_flags=wv["recomputed"], same_as_fill=wv["same"],
                              triangle=wv["T"], rest=wv["rest"], mesh="가상 시점 메시")
    axs[-1].set_xlabel("벽을 따른 거리 (m)")
    title = ("영상이 보지 못한 긴 벽은 본 방법에서 섰고 2차원 가우시안 스플래팅과 GeoGS에서는 조각만 섰다 — "
             "B173 주변 LoD2 긴 벽, 왼쪽 위 모래색은 학습 영상 한 장이 본 칸이라 셈에서 뺐다")
    ta = fig.suptitle(textwrap.fill(title, 88), fontsize=17, fontweight="bold", x=0.01, ha="left", y=1.005)
    R = cause["regions"]
    v = cause["views_on_face"][0]
    ex = extra["results"]
    foot = (f"B173 주변 LoD2. 긴 벽(LoD2 면 {w['surf_ext']}, 칸 {cause['face_cells']['all']:,}개, {R['face']['area_m2']:,.1f} m²)을 바깥에서 정면으로 본 것; "
            f"칸 하나는 패치 하나(0.25 m)의 제자리다. 파랑 = 결과 메시가 패치 중심 0.25 m 안에 있음(벽 있음), 흰 칸 = 없음, "
            f"옅은 회색 칸 = 뺀 칸(지금 지붕보다 위 {n_li[1]:,}개와 모호 {n_li[2]:,}개), 모래색 칸 = 학습 영상 {VIEW} 한 장이 화소를 놓아 "
            f"'학습 영상이 보지 못한 패치'에 들지 않은 칸 {int(out_set.sum()):,}개(앞 그림에서는 투명하게 남아 흰 칸 = 없음처럼 보였다), "
            f"회색 윤곽 = LoD2 면 {w['surf_ext']}의 범위, 검은 점 = 벽면 0.25 m 안의 참값 점 {len(gpt):,}개. "
            f"모래색 칸은 그 영상이 이 면을 보는 왼쪽 위 영역(칸 {R['T']['cells']:,}개, {R['T']['area_m2']:.1f} m², 면의 "
            f"{100 * R['T']['area_share_of_face']:.1f} %)의 {100 * R['T']['seen_share']:.1f} %이고, 나머지 {R['T']['unseen_set_patches']:,}칸이 보지 못한 패치로 "
            f"남아 대각선으로 듬성듬성하다(그 영상은 {v['distance_m']['median']:.0f} m 밖에서 벽 법선과 {v['incidence_deg_from_wall_normal']['median']:.0f}° "
            f"기울어 보고, 화소 하나가 벽에서 {v['pixel_footprint_m2']['median']:.3f} m², 칸 {v['cells_per_pixel_median']:.2f}개 넓이다). "
            f"이 자리의 벽 있음(맞음으로 미룬 {panels['본 방법']['patches']:,}패치, 빈칸 채우기 값과 같음): "
            + ", ".join(f"{I.PANELS[k][2]} {pct(panels[I.PANELS[k][0]]['share'])}" for k in range(3))
            + f"; 본 방법 씨앗 1 {pct(g('wall_virtual', 'm1'))}, 학습 전 사전 정보 {pct(g('wall_virtual', 'samepath'))}, "
            f"MVS 기반 결합 {pct(g('wall_virtual', 'mvsfuse'))}, 본 방법의 판정으로 갈아 끼운 변형 {pct(g('wall_virtual', 'judgefuse'))}"
            f"(SL/tables/virtual_main.json). 셈을 바꾼다면[이 발주에서 냄]: 모래색 영역을 통째로 빼면 본 방법 씨앗 0 "
            f"{pct(ex['prop_LoD2_s0']['without_T']['share'])}, 씨앗 1 {pct(ex['prop_LoD2_s1']['without_T']['share'])}; 모래색 칸도 같은 규칙으로 세면 "
            f"{pct(ex['prop_LoD2_s0']['with_every_cell_of_T']['share'])}, {pct(ex['prop_LoD2_s1']['with_every_cell_of_T']['share'])}"
            f"({ex['prop_LoD2_s0']['with_every_cell_of_T']['patches']:,}패치).")
    fig.text(0.01, 0.0, textwrap.fill(foot, FOOT_W), ha="left", va="top", fontsize=11.5, color=DARK)
    vals = dict(task_id="PHD-MAIN-FIXTEST-v1", item="일 7", key="unseen_1_v2", redraw_of="docs/experiments/phd/main_fill_v1/figures/items/unseen_1.png",
                site=I.SITE, prior="LoD2", mark="그림은 [이 발주에서 냄]; 패널의 값은 빈칸 채우기의 것(출처 value_source)",
                place=dict(face=int(w["surf_ext"]), face_cells=int(len(s)), unseen_set=int(in_set.sum()), counted_patches=n_li[0],
                           excluded_in_set={"지금 지붕보다 위": n_li[1], "모호": n_li[2]}, outside_set_one_view=int(out_set.sum()),
                           outside_set_label_by_rule={str(k): int((out_set & (li_rule == k)).sum()) for k in (0, 1, 2)},
                           view=VIEW, triangle=R["T"], rest=R["rest"], gt_points_on_wall=int(len(gpt)),
                           frame=dict(centre=w["centre"], t=w["t"], normal=w["normal"], s_range=w["s_range"], z_range=w["z_range"]),
                           source="S1/defs/fig_views_v1.json unseen_face; cells: S0/s61/box/B173nb_b10/LoD2/units.npz"),
                colours=dict(blue="벽 있음", white="없음", light_grey="뺀 칸(지금 지붕보다 위, 모호)", sand="학습 영상 한 장이 본 칸(보지 못한 패치가 아님)"),
                changes_from_fill=["모래색 칸 3,262개를 그림(앞 그림은 투명 = 흰 칸)", "래스터를 칸의 격자에 맞춤(칸 중심 = 래스터 칸 중심)"],
                panels=panels, others_from_fill={k: g("wall_virtual", k) for k in ("m1", "samepath", "mvsfuse", "judgefuse")},
                others_source="SL/tables/virtual_main.json units.B173nb_b10/LoD2 rows.wall_virtual",
                sensitivity_mark="[이 발주에서 냄]", sensitivity={r: {k: ex[r][k] for k in ("now_as_fill", "without_T", "with_every_cell_of_T")}
                                                               for r in ("prop_LoD2_s0", "prop_LoD2_s1")},
                title=title, foot=foot, scientific_verdict=None)
    save(fig, "unseen_1_v2", vals, ta)
    return vals


def draw_cause(w, C, cause, H):
    s, z, in_set, Tm = C["s"], C["z"], C["in_set"], C["T"]
    i, j, shape, ext = cell_raster(s, z)
    v = cause["views_on_face"][0]
    R = cause["regions"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(16, 7.4), gridspec_kw=dict(width_ratios=[1.35, 1.0]))
    fig.subplots_adjust(wspace=0.12, top=0.86, bottom=0.10, left=0.05, right=0.99)
    img = np.zeros(shape + (4,))
    for m, col in ((in_set, SET_GREY), (~in_set, SAND)):
        img[i[m], j[m], :3] = rgb(col)
        img[i[m], j[m], 3] = 1.0
    # (가) the left part of the face
    a1.imshow(img, origin="lower", extent=ext, interpolation="nearest", aspect="equal")
    a1.set_xlim(-40.8, -9.0)
    a1.set_ylim(ext[2] - 0.3, ext[3] + 0.3)
    zs, zz = (-32.25, -29.25), (-37.0, -35.0)            # the zoom window (cell edges: s centres at ...x.x995 - 0.125)
    zs = tuple(np.floor((np.array(zs) - ext[0]) / I.CELL) * I.CELL + ext[0])
    zz = tuple(np.floor((np.array(zz) - ext[2]) / I.CELL) * I.CELL + ext[2])
    a1.add_patch(plt.Rectangle((zs[0], zz[0]), zs[1] - zs[0], zz[1] - zz[0], fill=False, ec="#c0392b", lw=2.0, zorder=6))
    tag(a1, -27.6, -42.6, f"모래색: 학습 영상 한 장의 화소가 떨어진 칸 {int((~in_set).sum()):,}개", SAND_TEXT, size=11.5)
    tag(a1, -23.0, -27.2, "짙은 회색: 보지 못한 패치\n(모래색 영역 밖은 빈틈 없음)", DARK, size=11.5)
    a1.set_xlabel("벽을 따른 거리 (m)")
    a1.set_ylabel("높이 z (m)")
    a1.text(0.0, 1.02, "(가) 면 53의 왼쪽 부분: 보지 못한 패치와 그 영상이 본 칸", transform=a1.transAxes, ha="left", va="bottom", fontsize=12.5,
            fontweight="bold")
    # (나) the zoom: cells, the cell grid and the view's pixel hits
    a2.imshow(img, origin="lower", extent=ext, interpolation="nearest", aspect="equal")
    for x in np.arange(zs[0], zs[1] + 1e-6, I.CELL):
        a2.axvline(x, color="white", lw=0.8, zorder=3)
    for y in np.arange(zz[0], zz[1] + 1e-6, I.CELL):
        a2.axhline(y, color="white", lw=0.8, zorder=3)
    hm = (H["s"] >= zs[0] - 0.3) & (H["s"] <= zs[1] + 0.3) & (H["z"] >= zz[0] - 0.3) & (H["z"] <= zz[1] + 0.3)
    a2.scatter(H["s"][hm], H["z"][hm], s=22, c="black", lw=0, zorder=5)
    a2.set_xlim(zs)
    a2.set_ylim(zz)
    a2.set_xlabel("벽을 따른 거리 (m)")
    a2.text(0.0, 1.02, "(나) 빨간 상자를 키움: 검은 점 = 그 영상의 화소 중심이 벽에 닿은 곳", transform=a2.transAxes, ha="left", va="bottom",
            fontsize=12.5, fontweight="bold")
    for sp_ in a2.spines.values():
        sp_.set_edgecolor("#c0392b")
        sp_.set_linewidth(2.0)
    in_win = (s >= zs[0]) & (s <= zs[1]) & (z >= zz[0]) & (z <= zz[1])
    title = "왼쪽 위 바둑판은 학습 영상 한 장의 화소가 떨어지지 않은 칸만 '보지 못한 패치'로 남은 무늬다"
    ta = fig.suptitle(title, fontsize=17, fontweight="bold", x=0.01, ha="left", y=0.985)
    foot = (f"B173 주변 LoD2 면 {w['surf_ext']}, 칸 0.25 m. 학습 영상 {v['view']}만 이 면의 왼쪽 위 영역(칸 {R['T']['cells']:,}개, {R['T']['area_m2']:.1f} m², "
            f"면의 {100 * R['T']['area_share_of_face']:.1f} %)을 본다; 나머지는 그 영상의 화면 밖이다(그 영상의 화면 안에서 벽에 가린 칸 "
            f"{v['face_cells_in_image_outside_region']}개). 영상 격자 1024×741에서 그 영상은 벽을 {v['distance_m']['median']:.0f} m 밖, 벽 법선에서 "
            f"{v['incidence_deg_from_wall_normal']['median']:.0f}° 기울어 보므로 화소 하나가 벽에서 {v['pixel_footprint_m2']['median']:.3f} m²"
            f"(칸 {v['cells_per_pixel_median']:.2f}개)를 덮고, 이웃 화소 사이가 벽에서 (Δs, Δz) = "
            f"({v['pixel_step_on_wall_m']['along_image_row']['ds']:.2f}, {v['pixel_step_on_wall_m']['along_image_row']['dz']:.2f}) m와 "
            f"({v['pixel_step_on_wall_m']['along_image_column']['ds']:.2f}, {v['pixel_step_on_wall_m']['along_image_column']['dz']:.2f}) m다. "
            f"칸은 화소 중심이 하나라도 떨어지면 '본 칸'이 된다: 그 영역 칸의 {100 * R['T']['seen_share']:.1f} %({R['T']['seen_by_a_training_view']:,}칸)가 화소를 받았고 "
            f"(화소 1개 {v['pixels_per_hit_cell'].get('1', 0):,}칸, 2개 {v['pixels_per_hit_cell'].get('2', 0):,}칸, 면 전체), 화소가 비껴간 "
            f"{R['T']['unseen_set_patches']:,}칸만 보지 못한 패치로 남는다. 그 칸들의 가장 가까운 이웃은 {100 * R['T']['nn_spacing_unseen_set']['share_0_35']:.1f} %가 "
            f"대각선 0.354 m이고(나머지 영역은 {100 * R['rest']['nn_spacing_unseen_set']['share_0_25']:.2f} %가 0.25 m), "
            f"{100 * R['T']['unseen_set_4_neighbours_in_set']['share_0']:.1f} %는 상하좌우에 보지 못한 패치가 없다. 칸의 넓이(0.0625 m²), in_eval(모두 참), "
            f"칸 격자(면 하나, 그림 축과 {cause['store_grid']['grids'][0]['angle_e1_to_drawing_s_deg']:.3f}°)는 두 영역이 같다. "
            f"키운 상자: 칸 {int(in_win.sum())}개 중 모래색 {int((in_win & ~in_set).sum())}개, 짙은 회색 {int((in_win & in_set).sum())}개, 화소 {int(hm.sum())}개."
            " [이 발주에서 냄]")
    fig.text(0.01, 0.0, textwrap.fill(foot, FOOT_W), ha="left", va="top", fontsize=11.5, color=DARK)
    vals = dict(task_id="PHD-MAIN-FIXTEST-v1", item="일 7", key="unseen_1_cause", site=I.SITE, prior="LoD2", mark="[이 발주에서 냄]",
                view=v["view"], zoom_window=dict(s=list(zs), z=list(zz), cells=int(in_win.sum()), sand=int((in_win & ~in_set).sum()),
                                                 set=int((in_win & in_set).sum()), pixel_hits=int(hm.sum())),
                triangle=R["T"], rest=R["rest"], view_numbers={k: v[k] for k in v if k != "what_the_view_shows_there"},
                colours=dict(sand="학습 영상 한 장의 화소가 떨어진 칸(본 칸)", dark_grey="보지 못한 패치(unseen set)", black_dots="그 영상의 화소 중심이 벽에 닿은 곳"),
                title=title, foot=foot, scientific_verdict=None)
    save(fig, "unseen_1_cause", vals, ta)
    return vals


def main():
    T = I.Timer()
    w, un, face = I.wall_place()
    c0, t, nrm = I.frame(w)
    C = np.load(I.OUT / "cause_cells.npz")
    H = np.load(I.OUT / "view_hits.npz")
    cause = I.jload(I.OUT / "cause.json")
    extra = I.jload(I.OUT / "extra_flags.json")
    gpt = gt_on_wall(w, c0, t, nrm)
    T.mark("load")
    v2 = draw_v2(w, un, face, C, cause, extra, gpt)
    T.mark("unseen_1_v2")
    vc = draw_cause(w, C, cause, H)
    T.mark("unseen_1_cause")
    tab = dict(task_id="PHD-MAIN-FIXTEST-v1", item="일 7", what="그림 unseen_1의 듬성듬성한 칸: 까닭, 숫자, 다시 그린 그림, 벽 있음 값",
               mark="[이 발주에서 냄] (출처가 적힌 값은 그 출처에서 옮김)", site=I.SITE, face=int(w["surf_ext"]),
               cause=cause, sensitivity=extra, figures=dict(unseen_1_v2=dict(png="figures/item7/unseen_1_v2.png", json="figures/item7/unseen_1_v2.json"),
                                                            unseen_1_cause=dict(png="figures/item7/unseen_1_cause.png", json="figures/item7/unseen_1_cause.json")),
               fill_values_copied=dict(prop_LoD2_s0=0.919906, prop_LoD2_s1=0.926587,
                                       source="SL/work/virtual/metrics/B173nb_b10/prop_LoD2_s{0,1}__LoD2.json 'wall'.share"),
               runs=[ln.split() for ln in (I.OUT / "logs/queue.log").read_text().splitlines() if ln.strip()],
               runs_note="queue.log of run_item7.sh: end time (KST), tag, rc, seconds of the docker run; this draw run itself is the last line "
                         "only after it ends (see the report)",
               scientific_verdict=None)
    I.jdump(I.TAB / "item7_unseen1.json", tab)
    T.mark("table json")
    I.log("draw done", T.marks)
    print(json.dumps(dict(v2_title=v2["title"], cause_title=vc["title"], seconds=T.marks), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
