"""PHD-MAIN-VISCMP-v4 일 마: 의도 한눈에 (덧붙임 1). Per intent x case x method: diff = the method's 완전성 - the right data's 완전성;
allow = the case's criterion of the place (learning methods) or the place's pooled spread (결합); 됨 / 안 됨 / 판단 못함 by the rule of the
config (work_ma). Unrounded values: DM/tables/d4_counts.json (comps value, mean, criterion, pooled) and FT/tables/eval_ft.json (영상만).
  python a5_intent.py -> /docs/tables/의도_한눈에.md|json, /docs/figures/의도_한눈에.png|pdf   scientific_verdict: null"""
import numpy as np

import vc_common  # noqa: F401
import pf_geo as G
from vc_common import CFG, DOCS, FT, SD, jdump, jl, log, now

CASES = [("B0_b10", "LoD2"), ("B173nb_b10", "LoD2"), ("R1rep_b10", "LoD2"), ("B0_b10", "ALS"), ("B173nb_b10", "ALS"), ("R1rep_b10", "ALS")]
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
MKEY = {"2DGS": "twodgs", "GeoGS": "geogs", "결합": "mvsfuse", "CDGS": "cdgs", "본 방법": "method"}
LEARN = {"2DGS", "GeoGS", "CDGS", "본 방법"}
DRAFT = {"보정": [1, 1, 1, 0, 6], "보존": [1, 0, 5, 0, 1], "다듬기": [0, 0, 3, 0, 4], "상속(결측)": [1, 1, 3, 0, 1]}
DRAFT_UNSURE = {"보존": {("R1rep_b10/LoD2", "2DGS"), ("R1rep_b10/LoD2", "GeoGS"), ("R1rep_b10/LoD2", "본 방법")},
                "상속(결측)": {("B173nb_b10/ALS", "GeoGS"), ("R1rep_b10/ALS", "CDGS")}}


def main():
    C = jl(CFG); W = C["work_ma"]
    D4 = jl(SD / "tables/d4_counts.json")["data"]; E = jl(FT / "tables/eval_ft.json")["cases"]
    cells, rows = {}, []
    for intent, place, _ in W["intents"]:
        d = D4[place]["dist"]; pooled = float(d["pooled"])
        for site, prior in CASES:
            u = f"{site}/{prior}"; c = d["cases"][u]
            prior_v = float(c["comps"]["prior"]["value"]); img_v = float(E[u]["places"][place]["dist"]["imgonly"]["v"])
            base, bname = {"보정": (img_v, "영상만"), "보존": (prior_v, "학습 전 사전 정보"), "상속(결측)": (prior_v, "학습 전 사전 정보")}.get(intent) or \
                ((prior_v, "학습 전 사전 정보") if prior_v <= img_v else (img_v, "영상만"))
            for m in W["methods"]:
                k = MKEY[m]
                v = float(c["mean"]) if k == "method" else float(c["comps"][k]["value"])
                n = int(c["seeds"]["n"]) if k == "method" else int(c["comps"][k]["n"])
                allow = float(c["criterion"]) if m in LEARN else pooled
                diff = v - base
                if m in LEARN and abs(diff) <= allow and allow > base / 2:
                    j = "판단 못함"
                elif diff <= allow:
                    j = "됨"
                else:
                    j = "안 됨"
                cells[(intent, u, m)] = dict(intent=intent, place=place, case=u, method=m, value_cm=v, base_cm=base, base=bname, diff_cm=diff, allow_cm=allow,
                                             judgement=j, gt_points=n, prior_cm=prior_v, imgonly_cm=img_v, criterion_parts=c.get("criterion_parts"), pooled_cm=pooled)
                rows.append(cells[(intent, u, m)])
    # counts and the draft
    counts = {i: [sum(1 for (ii, u, mm), e in cells.items() if ii == i and mm == m and e["judgement"] == "됨") for m in W["methods"]] for i, _, _ in W["intents"]}
    unsure = {i: sorted([(u, mm) for (ii, u, mm), e in cells.items() if ii == i and e["judgement"] == "판단 못함"]) for i, _, _ in W["intents"]}
    near = sorted([e for e in rows if abs(e["diff_cm"] - e["allow_cm"]) <= 0.15], key=lambda e: abs(e["diff_cm"] - e["allow_cm"]))
    title_ok = counts["보정"][4] == 6 and counts["보존"][2] >= max(counts["보존"][j] for j in range(5) if j != 2)
    out = dict(task="PHD-MAIN-VISCMP-v4", work="일 마", made=now(), rule=W, cells=rows, counts=counts, unsure=unsure,
               draft=dict(counts=DRAFT, unsure={k: sorted(v) for k, v in DRAFT_UNSURE.items()}), counts_differ={i: counts[i] != DRAFT[i] for i in counts},
               near_boundary=near, title=W["title"], title_holds=title_ok, scientific_verdict=None)
    jdump(DOCS / "tables/의도_한눈에.json", out)
    L = ["# 의도 한눈에 — 칸 표 [이 발주에서 냄, 반올림 전 값]", "", f"- 만든 때 {out['made']}. 값 = 완전성(cm). 출처: 새 거리 지표 `tables/d4_counts.json`(방법과 학습 전 사전 정보, 기준), 고친 판 시험 `tables/eval_ft.json`(영상만).",
         "- 판정: 차 = 방법 − 맞는 자료의 기준. 허용 = 학습하는 방법은 그 곳·경우의 '달라졌다'의 기준, 결합은 그 곳의 모은 흔들림 폭. 판단 못함 = 학습하는 방법에서 |차| ≤ 허용이고 허용 > 기준의 절반.", ""]
    for intent, place, _ in W["intents"]:
        L += [f"## {intent} · {place}", "", "| 경우 | 기준 | 기준 값 | 방법 | 방법 값 | 차 | 허용 | 판정 | 참값 점 |", "|---|---|---:|---|---:|---:|---:|---|---:|"]
        for site, prior in CASES:
            u = f"{site}/{prior}"
            for m in W["methods"]:
                e = cells[(intent, u, m)]
                L.append(f"| {SITE_KO[site]} · {'LoD2' if prior == 'LoD2' else '항공 LiDAR'} | {e['base']} | {e['base_cm']:.2f} | {m} | {e['value_cm']:.2f} | {e['diff_cm']:+.2f} | {e['allow_cm']:.2f} | {e['judgement']} | {e['gt_points']:,} |")
        L += ["", f"- 됨의 수(2DGS, GeoGS, 결합, CDGS, 본 방법): {counts[intent]} — 초안 {DRAFT[intent]}{'' if counts[intent] == DRAFT[intent] else ' (다름)'}", ""]
    (DOCS / "tables/의도_한눈에.md").write_text("\n".join(L) + "\n")
    # figure
    plt = G.setup_plt()
    from matplotlib.patches import Rectangle
    cw, ch = W["size_cm"]
    fig = plt.figure(figsize=(cw / 2.54, ch / 2.54))
    fs = 7.0
    col = W["colours"]; sym = {"됨": "○", "안 됨": "×", "판단 못함": "?"}
    pos = [(0.03, 0.535), (0.52, 0.535), (0.03, 0.10), (0.52, 0.10)]       # [그리는 법만 바꿈, 첫 그림 뒤] the lower titles overlapped the upper panels
    pw, ph = 0.45, 0.295
    for (intent, place, bname), (x0, y0) in zip(W["intents"], pos):
        ax = fig.add_axes([x0 + 0.085, y0, pw - 0.085, ph]); ax.set_xlim(0, 7.4); ax.set_ylim(0, 5); ax.axis("off")
        xs = [0, 1, 2, 3.4, 4.4, 5.4]
        for i, m in enumerate(W["methods"]):
            y = 4 - i
            fig.text(x0 + 0.08, y0 + ph * (y + 0.5) / 5, m, ha="right", va="center", fontsize=fs + (0.5 if m == "본 방법" else 0), weight="bold" if m == "본 방법" else "normal")
            for j, (site, prior) in enumerate(CASES):
                e = cells[(intent, f"{site}/{prior}", m)]
                ax.add_patch(Rectangle((xs[j] + 0.05, y + 0.06), 0.9, 0.88, fc=col[e["judgement"]], ec="#333333" if m == "본 방법" else "#bbbbbb", lw=1.2 if m == "본 방법" else 0.4))
                ax.text(xs[j] + 0.5, y + 0.5, sym[e["judgement"]], ha="center", va="center", fontsize=fs + 2)
            ax.text(6.6, y + 0.5, f"{counts[intent][i]}", ha="center", va="center", fontsize=fs + 1, weight="bold" if m == "본 방법" else "normal")
        for j, (site, prior) in enumerate(CASES):
            ax.text(xs[j] + 0.5, 5.12, SITE_KO[site], ha="center", va="bottom", fontsize=fs - 0.5)
        ax.text(1.5, 5.62, "LoD2", ha="center", va="bottom", fontsize=fs); ax.text(4.9, 5.62, "항공 LiDAR", ha="center", va="bottom", fontsize=fs)
        ax.text(6.6, 5.12, "○ 수", ha="center", va="bottom", fontsize=fs - 0.5)
        pko = {"c11": "사전 정보가 틀린 곳", "img": "영상이 틀린 곳", "c2": "두 자료가 모두 맞는 곳", "c4": "결측 영역"}[place]
        fig.text(x0 + pw / 2 + 0.04, y0 + ph + 0.072, f"{intent} · {pko}", ha="center", va="bottom", fontsize=fs + 1.5, weight="bold")
        bshort = {"영상만": "영상만", "학습 전 사전 정보": "학습 전 사전 정보", "학습 전 사전 정보와 영상만 가운데 완전성이 작은 쪽": "학습 전 사전 정보와 영상만 가운데 완전성이 작은 쪽"}[bname]
        fig.text(x0 + pw / 2 + 0.04, y0 - 0.018, f"기준: {bshort}", ha="center", va="top", fontsize=fs - 0.5, color="#444444")
    fig.suptitle(W["title"], fontsize=fs + 2.5, y=0.985)
    fig.text(0.5, 0.012, "○ 맞는 자료만큼 참값에 가까움    × 맞는 자료보다 멂    ? 흔들림이 커서 판단 못함", ha="center", fontsize=fs)
    for e in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"의도_한눈에.{e}", dpi=300)
    plt.close(fig)
    log("counts", counts, "unsure", unsure, "title_holds", title_ok)


if __name__ == "__main__":
    main()
