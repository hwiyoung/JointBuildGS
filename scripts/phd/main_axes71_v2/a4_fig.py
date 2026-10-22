"""PHD-MAIN-AXES71-v2 일 4 figures A-D (jointbuildgs:dev, CPU; reads AX/tables/a4_axes.json and the config only).

  python a4_fig.py   -> /docs/figures/일4_그림A_두축.png|pdf|json, 일4_그림B_경우마다, 일4_그림C_평균거리, 일4_그림D_축1_m

A: 2 x 2 (rows LoD2 / 항공 LiDAR, three sites together; columns axis 1 in τ multiples, axis 2), y = 참값 기준 재현율 R(τ). B: the same per
case. C: A with y = 참값 기준 평균 거리 (cm, log scale). D: axis 1 in m (the 보정 cells), per prior. Lines: the results in the config order
and style (the two inputs grey dashed). Axis 2: '지킴' (보존 · 문턱 안) full colour, '놓음' (한계) the same colour light, 보존 · 거름 one
marker at the right ('거름'). Bins with fewer than 10,000 GT rows: hollow marker; fewer than 100: not drawn. A new result (the next fixed
version) is one more name in config results.order + style. [새로 그림] scientific_verdict: null."""
import numpy as np

import ax_map as MP
from ax_common import CFG, DOCS, ORDER, RES_KO, TAB, jdump, jl, log, now

ST = CFG["results"]["style"]
MASK_MODE = {}
LOW, STAR = CFG["axes"]["plot_low"], CFG["axes"]["plot_star"]


def val(d, rk, line, i, y):
    e = d[rk]["mean"][line][str(i)] if rk == "method" else d[rk][next(iter(d[rk]))][line][str(i)]
    if e.get("status") != "있음" or e["n_gt"] < LOW or e.get(y) is None:
        return None, 0
    v = e[y] * (100 if y == "R_tau" else 1)
    return v, e["n_gt"]


def draw(ax, d, line, labels, y, light=False, xoff=0.0, extra=None, dotted=False):
    for rk in ORDER:
        if rk not in d:
            continue
        s = ST[rk]
        xs, ys, ns = [], [], []
        for i in range(len(labels)):
            v, n = val(d, rk, line, i, y)
            if v is None:
                continue
            xs.append(i + xoff); ys.append(v); ns.append(n)
        if not xs:
            continue
        a = 0.35 if light else 1.0
        ax.plot(xs, ys, color=s["color"], ls=":" if dotted else s["ls"], lw=s["lw"] * (0.8 if (light or dotted) else 1.0), alpha=a, zorder=3 if rk == "method" else 2)
        for x, yv, n in zip(xs, ys, ns):
            ax.plot([x], [yv], marker=s["marker"], ms=3.6, color=s["color"], mfc=s["color"] if n >= STAR else "white", mew=0.8, alpha=a, ls="none",
                    zorder=3 if rk == "method" else 2)


def mask_point(ax, d, x, y):
    for rk in ORDER:
        if rk not in d:
            continue
        v, n = val(d, rk, "axis2_mask", 99, y)
        if v is None:
            continue
        s = ST[rk]
        ax.plot([x], [v], marker=s["marker"], ms=3.6, color=s["color"], mfc=s["color"] if n >= STAR else "white", mew=0.8, ls="none")


def panel(ax, d, axis, y, labels, title):
    if axis == "axis1_tau":
        draw(ax, d, "axis1_tau", labels["axis1_tau"], y)
        ax.set_xticks(range(len(labels["axis1_tau"]))); ax.set_xticklabels(labels["axis1_tau"], fontsize=5.5, rotation=40)
        ax.set_xlabel("사전 정보 어긋남 (τ의 배)", fontsize=6)
    elif axis == "axis1_m":
        draw(ax, d, "axis1_m", labels["axis1_m"], y)
        ax.set_xticks(range(len(labels["axis1_m"]))); ax.set_xticklabels(labels["axis1_m"], fontsize=5.5, rotation=40)
        ax.set_xlabel("사전 정보 어긋남 (m)", fontsize=6)
        ax.axvline(2.5, color="#999999", lw=0.6, ls=":", zorder=1)
    else:
        lb = labels["axis2"]
        draw(ax, d, "axis2_limit", lb, y, light=True)
        draw(ax, d, "axis2_keep", lb, y)
        if MASK_MODE.get("binned"):
            draw(ax, d, "axis2_mask", lb, y, dotted=True)
            ax.set_xticks(range(len(lb))); ax.set_xticklabels(lb, fontsize=5.5, rotation=40)
        else:
            mask_point(ax, d, len(lb) + 0.6, y)
            ax.set_xticks(list(range(len(lb))) + [len(lb) + 0.6]); ax.set_xticklabels(lb + ["거름"], fontsize=5.5, rotation=40)
        ax.set_xlabel("영상 깊이 어긋남 (τ의 배)", fontsize=6)
    ax.set_title(title, fontsize=6.5)
    ax.tick_params(labelsize=5.5, length=2)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="y", color="#eeeeee", lw=0.5)
    if y == "R_tau":
        ax.set_ylim(-3, 103)
        ax.set_ylabel("참값 기준 재현율 R(τ) (%)", fontsize=6)
    else:
        ax.set_yscale("log")
        ax.set_ylabel("참값 기준 평균 거리 (cm)", fontsize=6)


def legend(fig, y=0.005, ncol=8):
    from matplotlib.lines import Line2D
    hs = [Line2D([0], [0], color=ST[k]["color"], ls=ST[k]["ls"], lw=ST[k]["lw"], marker=ST[k]["marker"], ms=3.6, label=RES_KO[k]) for k in ORDER]
    hs.append(Line2D([0], [0], color="#c0392b", alpha=0.35, lw=1.2, label="옅은 선: 판정이 놓음(한계)"))
    if MASK_MODE.get("binned"):
        hs.append(Line2D([0], [0], color="#c0392b", ls=":", lw=1.2, label="점선: 보존 · 거름(거르기 전 어긋남)"))
    hs.append(Line2D([0], [0], color="#555555", marker="o", mfc="white", ls="none", ms=3.6, label="빈 표지: 참값 점 1만 미만"))
    fig.legend(handles=hs, loc="lower center", ncol=ncol, fontsize=5.5, frameon=False, bbox_to_anchor=(0.5, y))


def main():
    plt = MP.setup_plt()
    J = jl(TAB / "a4_axes.json")
    D, labels = J["data"], J["labels"]
    MASK_MODE["binned"] = all(v.get("axis2_mask_mode") == "거르기 전 어긋남" for v in J["info"].values())
    out = {}
    PK = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
    for nm, y in (("일4_그림A_두축", "R_tau"), ("일4_그림C_평균거리", "mean")):
        fig, axs = plt.subplots(2, 2, figsize=(17 / 2.54, 12 / 2.54))
        for r, p in enumerate(("LoD2", "ALS")):
            d = D[f"합/{p}"]
            panel(axs[r, 0], d, "axis1_tau", y, labels, f"{PK[p]} · 축 1: 영상 깊이가 맞는 곳")
            panel(axs[r, 1], d, "axis2", y, labels, f"{PK[p]} · 축 2: 사전 정보가 맞는 곳")
        fig.tight_layout(rect=(0, 0.07, 1, 1))
        legend(fig)
        for e in ("png", "pdf"):
            fig.savefig(DOCS / "figures" / f"{nm}.{e}", dpi=300)
        plt.close(fig)
        out[nm] = dict(y=y, panels="2 x 2: 사전 정보(세 지역 합) x 축")
    fig, axs = plt.subplots(3, 4, figsize=(17 / 2.54, 17 / 2.54))
    for r, s in enumerate(("B0_b10", "B173nb_b10", "R1rep_b10")):
        for j, p in enumerate(("LoD2", "ALS")):
            d = D[f"{s}/{p}"]
            sk = CFG["site_ko"][s]
            panel(axs[r, 2 * j], d, "axis1_tau", "R_tau", labels, f"{sk} · {PK[p]} · 축 1")
            panel(axs[r, 2 * j + 1], d, "axis2", "R_tau", labels, f"{sk} · {PK[p]} · 축 2")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    legend(fig, ncol=5)
    for e in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"일4_그림B_경우마다.{e}", dpi=300)
    plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(17 / 2.54, 6.5 / 2.54))
    for j, p in enumerate(("LoD2", "ALS")):
        panel(axs[j], D[f"합/{p}"], "axis1_m", "R_tau", labels, f"{PK[p]} · 축 1 (m, 보정 칸)")
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    legend(fig, ncol=5)
    for e in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"일4_그림D_축1_m.{e}", dpi=300)
    plt.close(fig)
    for nm in ("일4_그림A_두축", "일4_그림B_경우마다", "일4_그림C_평균거리", "일4_그림D_축1_m"):
        jdump(DOCS / "figures" / f"{nm}.json", dict(task="PHD-MAIN-AXES71-v2", work="일 4", made=now(), source="AX/tables/a4_axes.json (= tables/일4_두축.json)",
                                                   style=ST, order=ORDER, rule=__doc__.split("\n\n")[1], scientific_verdict=None))
    log("a4 figs done")


if __name__ == "__main__":
    main()
