"""PHD-CH6-SUPPORT-v1 task 5, the item 'prior slightly wrong' at the judgment level (jointbuildgs:dev, CPU): share of the area
released by the pre-training judgment per |GT - prior| / tau bin, on the measured patches (support) whose image is right
(codes 2 and 11), from /out/t5/judge/patches (t5_judge.py). Bins [0, 0.5), [0.5, 1) (prior right: a release is wrong) and
[1, 1.5), [1.5, 2), [2, 3), [3, 4), [4, 8), >= 8 (prior wrong: a release is right). The airborne LiDAR rule marks conflicts
only beyond 2 tau (margin_all_2), so its 1-2 tau bins are kept by design.

  python t5_bins.py

Writes /out/t5/judge/bins.json and bins.md, figs/fig_t5_bins.png. scientific_verdict: null."""
import json

import numpy as np

from ch6_common import BOXES, OUT, PRIOR_KO, PRIORS, RANGES, jdump, setup_fonts

J = OUT / "t5/judge"
EDGES = [0, 0.5, 1, 1.5, 2, 3, 4, 8, np.inf]
LAB = ["0~0.5", "0.5~1", "1~1.5", "1.5~2", "2~3", "3~4", "4~8", "8~"]


def main():
    out = {}
    for prior in PRIORS:
        for area_kind, runs in (("selection", RANGES), ("evaluation", ["B0_b10", "B173nb_b10", "R1rep_b10"])):
            rel_a = np.zeros(len(LAB)); tot_a = np.zeros(len(LAB))
            for r in runs:
                Z = np.load(J / "patches" / f"{r}_{prior}.npz")
                m = Z["sel"] & np.isin(Z["item"], (0, 1, 2))          # both right, prior wrong 1-4, prior wrong >= 4 (all support)
                ratio = np.abs(Z["med"].astype(np.float64)) / Z["tau"].astype(np.float64)
                b = np.digitize(ratio, EDGES[1:-1])
                a = Z["area"].astype(np.float64)
                for k in range(len(LAB)):
                    mm = m & (b == k)
                    tot_a[k] += a[mm].sum(); rel_a[k] += a[mm & Z["rel"]].sum()
            out[f"{area_kind}/{prior}"] = dict(bins=LAB, area_m2=[round(x, 1) for x in tot_a],
                                               released_share=[round(float(r_ / t_), 4) if t_ > 0 else None for r_, t_ in zip(rel_a, tot_a)])
    jdump(J / "bins.json", dict(rule=__doc__.split("\n\n")[0], **out, scientific_verdict=None))
    L = ["# 어긋남 크기별 놓은 몫 (학습 전 판정, 지지 패치, 영상이 맞는 곳)", "",
         "| 사전 정보 · 자리 | " + " | ".join(f"{b}τ" for b in LAB) + " |", "|---|" + "---|" * len(LAB)]
    for key, v in out.items():
        a_, p_ = key.split("/")
        L.append(f"| {PRIOR_KO[p_]} · {'고르는 곳' if a_ == 'selection' else '평가 지역'} | " +
                 " | ".join("—" if s is None else f"{100 * s:.0f} % ({a:,.0f})" for s, a in zip(v["released_share"], v["area_m2"])) + " |")
    L += ["", "- 칸: 놓은 넓이의 몫 (그 구간의 넓이 m²). 1τ 아래는 사전 정보가 맞으므로 놓으면 잘못 놓음, 1τ 위는 놓으면 맞게 놓음이다.",
          "- 항공 LiDAR의 최종 규칙은 2τ를 넘을 때만 충돌로 표시한다. 그래서 1~2τ는 설계대로 지킨다."]
    (J / "bins.md").write_text("\n".join(L) + "\n")
    plt = setup_fonts()
    fig, ax = plt.subplots(figsize=(8.5, 4.4), constrained_layout=True)
    x = np.arange(len(LAB))
    for key, v in out.items():
        a_, p_ = key.split("/")
        y = [np.nan if s is None else 100 * s for s in v["released_share"]]
        ax.plot(x, y, "-o" if a_ == "selection" else "--s", color="#1f77b4" if p_ == "LoD2" else "#d35400", ms=5,
                label=f"{PRIOR_KO[p_]} · {'고르는 곳' if a_ == 'selection' else '평가 지역'}")
    ax.axvline(1.5, color="k", lw=0.8); ax.text(1.55, 5, "← 사전 정보 맞음 | 틀림 →", fontsize=8.5)
    ax.axvspan(1.5, 5.5, color="#f5f5f5", zorder=0); ax.text(3.5, 92, "조금 틀린 곳 (1~4τ)", ha="center", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels([f"{b}τ" for b in LAB]); ax.set_ylim(0, 102); ax.set_ylabel("학습 전 판정이 놓은 넓이 (%)")
    ax.set_xlabel("|참값 − 사전 정보| / τ"); ax.legend(fontsize=8, frameon=False, loc="center right"); ax.grid(alpha=0.3)
    ax.set_title("어긋남 크기별로 학습 전 판정이 사전 정보를 놓은 몫", fontsize=11, loc="left")
    fig.savefig(J / "figs" / "fig_t5_bins.png", dpi=150); plt.close(fig)
    print("\n".join(L))


if __name__ == "__main__":
    main()
