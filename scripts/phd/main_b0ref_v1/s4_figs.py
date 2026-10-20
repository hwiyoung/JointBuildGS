"""PHD-MAIN-B0REF-v1 figures 1~3 (config figures_9_2; places fixed from the LoD2 and the evaluation range before any count).
(jointbuildgs:dev, CPU)

  python s4_figs.py [1] [2] [3]   -> /docs/figures/fig<k>_*.png|pdf and fig<k>_*.json (the numbers under each figure)

fig1: the figure face (ext 22, the target-building wall with the largest area in the evaluation range) seen from outside (right = along
      the wall, up = height); 0.25 m cells coloured by the number of space-selected points; panels GeoGS / raw ULS all returns / the
      study's wall points (vertical & single return); one log colour range for the three.
fig2: (가) top view of the evaluation range in box axes (u, v), 0.25 m cells, median distance of the GeoGS points of the cell to the raw
      ULS (all returns); (나) the figure face from outside, the same distance; 0-10 cm continuous, above 10 cm one colour.
fig3: cumulative share of the GeoGS-to-cloud distance, roof / low wall (0-3 m) / high wall (10 m and up); raw ULS solid, the other
      clouds dashed. [이 요청에서 냄] scientific_verdict: null."""
import sys

import numpy as np

from b0_common import B0, CFG, DOCS, box_def, jdump, jl, load_crop, lod2_faces, now, wall_axes, xy_to_uv

FIG = DOCS / "figures"
FACE = CFG["figures_9_2"]["fig1"]["face_ext"]
CELL = CFG["figures_9_2"]["fig1"]["cell_m"]


def setup():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
        try:
            font_manager.fontManager.addfont(f)
        except Exception:
            pass
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def face_geom():
    f = [f for f in lod2_faces() if f["ext"] == FACE][0]
    n, t = wall_axes(f)
    T2 = np.stack([(f["tris"] - f["origin"]) @ t, f["tris"][..., 2]], -1)
    return f, T2


def face_grid(T2):
    lo, hi = T2.reshape(-1, 2).min(0), T2.reshape(-1, 2).max(0)
    es = np.arange(np.floor(lo[0] / CELL) * CELL, hi[0] + CELL, CELL)
    ez = np.arange(np.floor(lo[1] / CELL) * CELL, hi[1] + CELL, CELL)
    return es, ez


def outline(ax, T2, **kw):
    from matplotlib.patches import Polygon
    for tri in T2:
        ax.add_patch(Polygon(tri, closed=True, fill=False, lw=0.3, ec="0.6", **kw))


def fig1(plt):
    from matplotlib.colors import LogNorm
    f, T2 = face_geom()
    es, ez = face_grid(T2)
    F = {r["ext"]: r for r in jl(B0 / "prep/faces.json")["faces"]}
    area = F[FACE]["area_space_in_eval_m2"]
    panels = []
    for key, label, name, extra in (("geogs", "GeoGS 점군", "geogs", None), ("all", "원래 드론 LiDAR 모든 반사", "uls_nadir", None),
                                   ("study", "이 연구의 벽 점(수직면·단일 반사)", "uls_nadir", "study")):
        X = load_crop(name)["xyz"]; S = np.load(B0 / "sel" / f"{name}.npz")
        idx = S[f"face_{FACE}"]
        if extra == "study":
            idx = idx[S["vert"][idx] & (S["rclass"][idx] == 0)]
        n, t = wall_axes(f)
        s = (X[idx] - f["origin"]) @ t; z = X[idx, 2]
        H, _, _ = np.histogram2d(s, z, bins=[es, ez])
        panels.append(dict(key=key, label=label, points=int(len(idx)), per_m2=len(idx) / area, H=H,
                           cells_with_points=int((H > 0).sum()), cells_total_in_face=None))
    vmax = max(p["H"].max() for p in panels)
    fig, axs = plt.subplots(3, 1, figsize=(12, 11.5), constrained_layout=True)
    for ax, p, lab in zip(axs, panels, ("(가)", "(나)", "(다)")):
        Hm = np.ma.masked_equal(p["H"], 0)
        im = ax.pcolormesh(es, ez, Hm.T, norm=LogNorm(vmin=1, vmax=vmax), cmap="viridis", shading="flat")
        outline(ax, T2)
        ax.set_aspect("equal"); ax.set_xlim(es[0], es[-1]); ax.set_ylim(ez[0], ez[-1])
        ax.text(0.01, 0.97, f"{lab} {p['label']}: {p['points']:,}점, {p['per_m2']:,.0f}점/m², 점이 있는 칸 {p['cells_with_points']:,}",
                transform=ax.transAxes, va="top", ha="left", fontsize=11, color="k", bbox=dict(fc="w", ec="none", alpha=0.85))
        ax.set_ylabel("높이 z (m, 작업 좌표)")
    axs[-1].set_xlabel("벽을 따라 (m; 바깥에서 본 오른쪽이 +)")
    cb = fig.colorbar(im, ax=axs, shrink=0.6, location="right")
    cb.set_label("0.25 m 칸의 점 수(로그)")
    fig.suptitle(f"벽 점이 어느 자료에 얼마나 있는가 — 대상 건물 벽면 {FACE}({F[FACE]['facing']}향, 공간 넓이 {area:,.0f} m²)을 바깥에서 봄", fontsize=13)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"fig1_wall_counts.{ext}", dpi=150)
    plt.close(fig)
    rec = dict(title="벽 점이 어느 자료에 얼마나 있는가", face=FACE, facing=F[FACE]["facing"], area_space_m2=area, cell_m=CELL,
               panels=[{k: v for k, v in p.items() if k != "H"} for p in panels], color_range=[1, float(vmax)],
               caption="(가) GeoGS 점군, (나) 원래 드론 LiDAR(연직 비행) 모든 반사, (다) 이 연구의 벽 점(원래 드론 LiDAR의 수직면 판정 & 단일 반사). "
                       "세 칸 모두 벽면 공간(수평 1.0 m 안, 아래 끝 + 0.5 m ~ 위 끝 − 0.5 m, 평가 범위 안)의 점.",
               numbers_line=" · ".join(f"{p['label']} {p['points']:,}점 ({p['per_m2']:,.1f}/m²)" for p in panels), made=now(), scientific_verdict=None)
    jdump(FIG / "fig1_wall_counts.json", rec)
    print(rec["numbers_line"])


def median_grid(a, b, v, ea, eb):
    ia = np.clip(np.digitize(a, ea) - 1, 0, len(ea) - 2); ib = np.clip(np.digitize(b, eb) - 1, 0, len(eb) - 2)
    ok = (a >= ea[0]) & (a < ea[-1]) & (b >= eb[0]) & (b < eb[-1])
    key = ia[ok] * (len(eb) - 1) + ib[ok]; vv = v[ok]
    o = np.argsort(key, kind="stable"); key, vv = key[o], vv[o]
    u, st, c = np.unique(key, return_index=True, return_counts=True)
    M = np.full((len(ea) - 1) * (len(eb) - 1), np.nan)
    M[u] = [np.median(vv[s:s + n]) for s, n in zip(st, c)]
    return M.reshape(len(ea) - 1, len(eb) - 1)


def fig2(plt, target="uls_nadir"):
    from matplotlib.colors import ListedColormap
    import matplotlib
    G = load_crop("geogs")["xyz"]
    z = np.load(B0 / "dist" / f"geogs__{target}.npz")
    S = np.load(B0 / "sel/geogs.npz")
    rows = z["ev_rows"]; d = z["d"].astype(np.float64)
    b = box_def()
    uv = xy_to_uv(G[rows, :2])
    eu = np.arange(b["eval_u"][0], b["eval_u"][1] + CELL, CELL); evv = np.arange(b["eval_v"][0], b["eval_v"][1] + CELL, CELL)
    Mt = median_grid(uv[:, 0], uv[:, 1], d, eu, evv)
    f, T2 = face_geom(); es, ez = face_grid(T2)
    n, t = wall_axes(f)
    fi = S[f"face_{FACE}"]
    pos = np.searchsorted(rows, fi)
    ok = (pos < len(rows)) & (rows[np.minimum(pos, len(rows) - 1)] == fi)
    fd = d[pos[ok]]; fx = G[fi[ok]]
    Mf = median_grid((fx - f["origin"]) @ t, fx[:, 2], fd, es, ez)
    cmap = matplotlib.colormaps["viridis"].copy(); cmap.set_over("#d62728"); cmap.set_bad("white")
    fig, axs = plt.subplots(2, 1, figsize=(12, 10.5), constrained_layout=True, gridspec_kw=dict(height_ratios=[31, 21]))
    im = axs[0].pcolormesh(eu, evv, (Mt.T * 100), cmap=cmap, vmin=0, vmax=10, shading="flat")
    axs[0].set_aspect("equal"); axs[0].set_xlabel("u (m, 상자 축)"); axs[0].set_ylabel("v (m)")
    axs[1].pcolormesh(es, ez, (Mf.T * 100), cmap=cmap, vmin=0, vmax=10, shading="flat")
    outline(axs[1], T2); axs[1].set_aspect("equal"); axs[1].set_xlim(es[0], es[-1]); axs[1].set_ylim(ez[0], ez[-1])
    axs[1].set_xlabel("벽을 따라 (m)"); axs[1].set_ylabel("높이 z (m)")
    roof = S["roof_any"][rows]; wall = S["wall_any"][rows]
    num = dict(all_median_m=float(np.median(d)), roof_median_m=float(np.median(d[roof])), wall_median_m=float(np.median(d[wall])),
               face_median_m=float(np.median(fd)), face_points=int(len(fd)), points=int(len(d)),
               share_over_10cm_all=float(np.mean(d > 0.1)), share_over_10cm_face=float(np.mean(fd > 0.1)))
    axs[0].text(0.01, 0.97, f"(가) 위에서 본 평가 범위: GeoGS 점 {num['points']:,}, 중앙값 {num['all_median_m']*100:.1f} cm, 10 cm 넘음 {num['share_over_10cm_all']*100:.0f} %",
                transform=axs[0].transAxes, va="top", fontsize=11, bbox=dict(fc="w", ec="none", alpha=0.85))
    axs[1].text(0.01, 0.97, f"(나) 벽면 {FACE} 정면: GeoGS 점 {num['face_points']:,}, 중앙값 {num['face_median_m']*100:.1f} cm, 10 cm 넘음 {num['share_over_10cm_face']*100:.0f} %",
                transform=axs[1].transAxes, va="top", fontsize=11, bbox=dict(fc="w", ec="none", alpha=0.85))
    cb = fig.colorbar(im, ax=axs, shrink=0.6, extend="max"); cb.set_label("칸의 거리 중앙값 (cm; 빨강 = 10 cm 넘음)")
    fig.suptitle("GeoGS 점이 원래 드론 LiDAR(연직 비행, 모든 반사)에서 얼마나 떨어져 있는가", fontsize=13)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"fig2_distance_map.{ext}", dpi=150)
    plt.close(fig)
    rec = dict(title="GeoGS 점이 원래 드론 LiDAR에서 얼마나 떨어져 있는가", target=target, cell_m=CELL, numbers=num,
               caption="(가) 대상 건물 평가 범위를 위에서 본 지도(상자 축 u, v; 칸마다 그 칸의 GeoGS 점의 거리 중앙값), (나) 그림 1의 벽면을 바깥에서 본 정면.",
               numbers_line=f"전체 중앙값 {num['all_median_m']*100:.1f} cm (n = {num['points']:,}) · 지붕 {num['roof_median_m']*100:.1f} cm · 벽 {num['wall_median_m']*100:.1f} cm · 벽면 {FACE} {num['face_median_m']*100:.1f} cm (n = {num['face_points']:,})",
               made=now(), scientific_verdict=None)
    jdump(FIG / "fig2_distance_map.json", rec)
    print(rec["numbers_line"])


def fig3(plt):
    """[결과를 본 뒤 고침] x range 1e-6 .. 10 m (the matched file sits at 0.004-0.033 mm, below the first plan's 0.1 mm start);
    labels written next to the curves instead of a crowded list."""
    T = jl(DOCS / "tables/t3_dist.json")
    S = np.load(B0 / "sel/geogs.npz")
    h = S["wall_h"]
    places = [("roof", "지붕", S["roof_any"], "#1f77b4"), ("low", "낮은 벽 0~3 m", S["wall_any"] & (h < 3), "#2ca02c"),
              ("high", "높은 벽 10 m 위", S["wall_any"] & (h >= 10), "#d62728")]
    main = "uls_nadir"
    others = [t for t in ("uls_manual_v120", "fill_v120", "photogrammetry") if t in T["targets"]]
    styles = {main: "-", "uls_manual_v120": "--", "fill_v120": ":", "photogrammetry": "-."}
    names = {"-": "실선", "--": "파선", ":": "점선", "-.": "점쇄선"}
    xs = np.logspace(-6, 1, 500)
    fig, ax = plt.subplots(figsize=(11.5, 6.8), constrained_layout=True)
    curves = []
    for tg in [main] + others:
        z = np.load(B0 / "dist" / f"geogs__{tg}.npz")
        rows = z["ev_rows"]; d = z["d"].astype(np.float64)
        for key, lab, m, col in places:
            dm = np.sort(d[m[rows]])
            y = np.searchsorted(dm, xs, side="right") / len(dm)
            ax.plot(xs, y * 100, ls=styles[tg], color=col, lw=2.0 if tg in (main, "uls_manual_v120") else 1.2)
            curves.append(dict(target=tg, target_label=T["labels"][tg], place=lab, n=int(len(dm)), median_m=float(np.median(dm)),
                               share_le_1mm=float(np.mean(dm <= 0.001)), share_le_1cm=float(np.mean(dm <= 0.01)), share_le_5cm=float(np.mean(dm <= 0.05))))
    ax.set_xscale("log"); ax.set_xlim(1e-6, 10); ax.set_ylim(0, 102)
    ax.set_xlabel("가장 가까운 점까지의 거리 (m, 로그)"); ax.set_ylabel("그 거리 안에 든 GeoGS 점의 몫 (%)")
    ax.grid(True, which="both", lw=0.3, alpha=0.5)
    ax.text(4e-5, 50, "수동 비행 판 1.2.0 (파선)\n세 곳 모두 0.04 mm 안에 100 %", fontsize=10, va="center")
    ax.text(1.2e-3, 92, "5 mm 처리본 판 1.2.0 (점선): 벽 88~90 %, 지붕 3 %", fontsize=9.5, va="bottom")
    ax.text(0.06, 55, "연직 비행 (실선)\n지붕 중앙값 3.8 cm", fontsize=10, color="#1f77b4")
    ax.text(0.25, 20, "연직 비행 (실선): 벽은\n대부분 1 m 넘게 떨어짐", fontsize=10, color="#2ca02c")
    ax.text(1e-6 * 1.5, 99, "색: 파랑 지붕 · 초록 낮은 벽(0~3 m) · 빨강 높은 벽(10 m 위)   선: " +
            " · ".join(f"{T['labels'][t]} {names[styles[t]]}" for t in [main] + others), fontsize=8.5, va="top",
            bbox=dict(fc="w", ec="none", alpha=0.9))
    ax.set_title("거리가 곳마다 어떻게 퍼지는가 — GeoGS 점에서 각 점군의 가장 가까운 점까지", fontsize=13)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"fig3_distance_cdf.{ext}", dpi=150)
    plt.close(fig)
    rec = dict(title="거리가 곳마다 어떻게 퍼지는가", curves=curves, x_range_m=[1e-6, 10],
               note="결과를 본 뒤 고침: 가로축을 0.1 mm~1 m에서 1 µm~10 m로 넓힘(짝이 된 파일까지의 거리가 0.004~0.033 mm)",
               numbers_line=" · ".join(f"{c['place']}→{c['target_label']} 중앙값 {c['median_m']*1e3:.3f} mm" for c in curves if c["target"] in (main, "uls_manual_v120")),
               made=now(), scientific_verdict=None)
    jdump(FIG / "fig3_distance_cdf.json", rec)
    print(rec["numbers_line"])


if __name__ == "__main__":
    plt = setup()
    which = sys.argv[1:] or ["1", "2", "3"]
    if "1" in which:
        fig1(plt)
    if "2" in which:
        fig2(plt)
    if "3" in which:
        fig3(plt)
