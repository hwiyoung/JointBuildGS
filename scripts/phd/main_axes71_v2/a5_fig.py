"""PHD-MAIN-AXES71-v2 figures of 일 5 (cumulative distributions), 일 6 (clump boxes) and 일 7 (boundary distance) (jointbuildgs:dev, CPU;
reads AX/tables/a5_cdf.json, a6_clumps.json, a7_boundary.json and the config only).

  python a5_fig.py   -> /docs/figures/일5_누적분포_<합|case>.png|pdf|json, 일5_누적분포_결과기준_<합>.png|pdf, 일6_덩어리상자_<prior>.png|pdf,
                        일7_경계거리_<prior>.png|pdf
일 5: per cell (config cdf.cells) one panel, x = |d_g| / τ (0~8), y = share of GT points (%), one line per result (config order and style),
dotted vertical at 1 (τ) and horizontal at 50 %. Per prior (three sites) and per case; the result side (셈 마) per prior (appendix).
일 6: per cell x prior, the clumps of 2.5 m2 or more: one box per result of the clumps' R(τ), points = clumps. 일 7: per cell (config
boundary.cells_fig) one panel, x = boundary distance bin, y = R(τ). [새로 그림] scientific_verdict: null."""
import numpy as np

import ax_map as MP
from ax_common import CASES, CFG, DOCS, KEY_KO, ORDER, PRIORS, RES_KO, TAB, case_ko, jdump, jl, log, now

ST = CFG["results"]["style"]
PK = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}


def legend(fig, ncol=7, y=0.0):
    from matplotlib.lines import Line2D
    hs = [Line2D([0], [0], color=ST[k]["color"], ls=ST[k]["ls"], lw=ST[k]["lw"], label=RES_KO[k]) for k in ORDER]
    fig.legend(handles=hs, loc="lower center", ncol=ncol, fontsize=6, frameon=False, bbox_to_anchor=(0.5, y))


def cdf_fig(plt, d, grid, cells, title, stem, side="gt"):
    n = len(cells)
    nc = 4
    nr = int(np.ceil(n / nc))
    fig, axs = plt.subplots(nr, nc, figsize=(17 / 2.54, 4.6 * nr / 2.54 + 1.2), squeeze=False)
    rec = {}
    for i, c in enumerate(cells):
        ax = axs[i // nc, i % nc]
        nshow = None
        for rk in ORDER:
            if rk not in d:
                continue
            vals = [d[rk][r][c] for r in d[rk]]
            if any(v.get("status") != "있음" for v in vals):
                continue
            g = [v[side] for v in vals]
            if g[0]["n"] < 100:
                continue
            y = 100 * np.mean([x["cdf"] for x in g], 0)
            ax.plot(grid, y, color=ST[rk]["color"], ls=ST[rk]["ls"], lw=ST[rk]["lw"] * 0.8)
            nshow = g[0]["n"]
            rec.setdefault(c, {})[rk] = dict(n=g[0]["n"], at_tau=float(np.interp(1.0, grid, y)), at_4tau=float(np.interp(4.0, grid, y)))
        ax.axvline(1, color="#888888", lw=0.6, ls=":")
        ax.axhline(50, color="#888888", lw=0.6, ls=":")
        ax.set_xlim(0, grid[-1]); ax.set_ylim(0, 100)
        ax.set_title(KEY_KO[c] + ("" if nshow is None else f" ({nshow:,}점)") if nshow else KEY_KO[c] + " (표본 부족)", fontsize=6.5)
        ax.tick_params(labelsize=5.5, length=2)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        if i % nc == 0:
            ax.set_ylabel("누적 비율 (%)", fontsize=6)
        ax.set_xlabel(("|d_g|" if side == "gt" else "결과 기준 거리") + " ÷ τ", fontsize=6)
    for j in range(n, nr * nc):
        axs[j // nc, j % nc].set_axis_off()
    fig.suptitle(title, fontsize=7.5)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    legend(fig)
    for e in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"{stem}.{e}", dpi=300)
    plt.close(fig)
    jdump(DOCS / "figures" / f"{stem}.json", dict(task="PHD-MAIN-AXES71-v2", made=now(), title=title, side=side, values=rec, source="AX/tables/a5_cdf.json", scientific_verdict=None))


def main():
    plt = MP.setup_plt()
    J = jl(TAB / "a5_cdf.json")
    grid = np.asarray(J["grid_tau"])
    cells = CFG["cdf"]["cells"]
    for u, d in J["data"].items():
        if u.startswith("합"):
            p = u.split("/")[1]
            cdf_fig(plt, d, grid, cells, f"{PK[p]} · 세 지역 합 · 참값 기준", f"일5_누적분포_{p}_합")
            cdf_fig(plt, d, grid, cells, f"{PK[p]} · 세 지역 합 · 결과 기준(셈 마)", f"일5_누적분포_결과기준_{p}_합", side="res")
        else:
            s, p = u.split("/")
            cdf_fig(plt, d, grid, cells, f"{case_ko(s, p)} · 참값 기준", f"일5_누적분포_{s}_{p}")
    log("cdf figs")
    # 일 6 boxes
    K = jl(TAB / "a6_clumps.json")["data"]["values"]
    for p in PRIORS:
        d = K[f"합/{p}"]
        r0 = next(iter(d["method"]))
        cs = [c for c in d["method"][r0].get("clumps", {}) if np.sum(np.asarray(d["method"][r0]["clumps"][c]["area"]) >= 2.5) >= 3]
        if not cs:
            continue
        fig, axs = plt.subplots(1, len(cs), figsize=(17 / 2.54, 6 / 2.54), squeeze=False)
        rec = {}
        for i, c in enumerate(cs):
            ax = axs[0, i]
            data, cols, labs = [], [], []
            for rk in ORDER:
                if rk not in d or d[rk][next(iter(d[rk]))].get("status") != "있음":
                    continue
                arrs = []
                for r in d[rk]:
                    e = d[rk][r]["clumps"][c]
                    a = np.asarray(e["area"]); R = np.asarray(e["R_tau"])
                    arrs.append(R[a >= 2.5])
                v = 100 * np.mean(arrs, 0)
                data.append(v); cols.append(ST[rk]["color"]); labs.append(RES_KO[rk])
                rec.setdefault(c, {})[rk] = dict(clumps=int(len(v)), median=float(np.median(v)), q25=float(np.percentile(v, 25)), q75=float(np.percentile(v, 75)))
            bp = ax.boxplot(data, widths=0.6, showfliers=False, patch_artist=True, medianprops=dict(color="k", lw=0.8))
            for b, col in zip(bp["boxes"], cols):
                b.set_facecolor(col); b.set_alpha(0.35); b.set_edgecolor(col)
            for x, (v, col) in enumerate(zip(data, cols)):
                ax.scatter(np.full(len(v), x + 1) + np.random.default_rng(0).uniform(-0.18, 0.18, len(v)), v, s=2, color=col, lw=0, zorder=3)
            ax.set_xticks(range(1, len(labs) + 1)); ax.set_xticklabels(labs, rotation=60, fontsize=5)
            ax.set_ylim(-3, 103); ax.set_title(f"{KEY_KO[c]} ({len(data[0])}덩어리)", fontsize=6.5)
            ax.tick_params(labelsize=5.5, length=2)
            if i == 0:
                ax.set_ylabel("덩어리마다 R(τ) (%)", fontsize=6)
        fig.suptitle(f"{PK[p]} · 세 지역 합 · 2.5 m² 이상 덩어리", fontsize=7.5)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        for e in ("png", "pdf"):
            fig.savefig(DOCS / "figures" / f"일6_덩어리상자_{p}.{e}", dpi=300)
        plt.close(fig)
        jdump(DOCS / "figures" / f"일6_덩어리상자_{p}.json", dict(task="PHD-MAIN-AXES71-v2", made=now(), values=rec, source="AX/tables/a6_clumps.json", scientific_verdict=None))
    log("clump boxes")
    # 일 7 boundary
    B = jl(TAB / "a7_boundary.json")
    labs = B["bins"]
    for p in PRIORS:
        d = B["data"][f"합/{p}"]
        cs = CFG["boundary"]["cells_fig"]
        fig, axs = plt.subplots(1, len(cs), figsize=(17 / 2.54, 5.5 / 2.54), squeeze=False, sharey=True)
        rec = {}
        for i, c in enumerate(cs):
            ax = axs[0, i]
            for rk in ORDER:
                if rk not in d or d[rk][next(iter(d[rk]))].get("status") != "있음":
                    continue
                xs, ys, ns = [], [], []
                for bi, lb in enumerate(labs):
                    es = [d[rk][r]["values"][c][lb] for r in d[rk]]
                    if es[0]["rows"] < 100 or es[0]["R_tau"] is None:
                        continue
                    xs.append(bi); ys.append(100 * np.mean([e["R_tau"] for e in es])); ns.append(es[0]["rows"])
                if not xs:
                    continue
                ax.plot(xs, ys, color=ST[rk]["color"], ls=ST[rk]["ls"], lw=ST[rk]["lw"] * 0.8, marker=ST[rk]["marker"], ms=2.5,
                        mfc=ST[rk]["color"])
                for x_, y_, n_ in zip(xs, ys, ns):
                    if n_ < 10000:
                        ax.plot([x_], [y_], marker=ST[rk]["marker"], ms=2.5, color=ST[rk]["color"], mfc="white", ls="none")
                rec.setdefault(c, {})[rk] = dict(zip([labs[x] for x in xs], ys))
            ax.set_xticks(range(len(labs))); ax.set_xticklabels(labs, fontsize=5, rotation=45)
            ax.set_ylim(-3, 103); ax.set_title(KEY_KO[c], fontsize=6.5)
            ax.set_xlabel("경계 거리 (m)", fontsize=6)
            ax.tick_params(labelsize=5.5, length=2)
            if i == 0:
                ax.set_ylabel("참값 기준 재현율 R(τ) (%)", fontsize=6)
        fig.suptitle(f"{PK[p]} · 세 지역 합", fontsize=7.5)
        fig.tight_layout(rect=(0, 0.1, 1, 0.95))
        legend(fig)
        for e in ("png", "pdf"):
            fig.savefig(DOCS / "figures" / f"일7_경계거리_{p}.{e}", dpi=300)
        plt.close(fig)
        jdump(DOCS / "figures" / f"일7_경계거리_{p}.json", dict(task="PHD-MAIN-AXES71-v2", made=now(), values=rec, source="AX/tables/a7_boundary.json", scientific_verdict=None))
    log("boundary figs")


if __name__ == "__main__":
    main()
