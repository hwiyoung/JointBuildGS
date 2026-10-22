"""PHD-MAIN-AXES71-v2 일 3 '맞춰 볼 값' (order 6): this task's values against the earlier records (jointbuildgs:dev, CPU).

  python a3c_checks.py   -> AX/tables/a3_checks.json, /docs/tables/일3_맞춰볼값.md|json

(1) The order's numbers (6, last item): 다듬기 R(τ) of the method (fix-test numbers), 보정 합 and 보존 합 R(τ) of the method and the prior,
보정 합 median |d_g| of the method and 결합 (v4 의도 한눈에). (2) Every cell that equals an earlier place (보정 합 = 사전 정보가 틀린 곳 c11,
보정 · 1~4τ = 조금 틀린 곳 c11s, 보존 합 = 영상이 틀린 곳 img; 다듬기 vs 두 자료가 모두 맞는 곳 c2 differs by the code-2 patches of
보존 · 거름, so it is listed as a comparison, not a check): R(τ), R(0.2 m), the median |d_g| ('거리' of the distance task) and P(0.2 m) 셈 가
against DM/tables/d3_metrics.json, per case and result; and the median |d_g| against v4 의도 한눈에 (반올림 전). Same = |diff| < 0.051 in
the shown unit (the order's one-decimal numbers) or < 1e-6 (unrounded records). [이 발주에서 냄] scientific_verdict: null."""
import numpy as np

from ax_common import CASES, DM, DOCS, RES_KO, TAB, case_ko, jdump, jl, now

MAP = {"s_corr": "c11", "c_corr14": "c11s", "s_keep": "img", "c_refine": "c2"}
DMK = {"prior": "prior", "geogs": "geogs", "twodgs": "twodgs", "mvsfuse": "mvsfuse", "cdgs": "cdgs", "method": "method"}
ORDER_VALS = [("c_refine", "B0_b10/LoD2", "method", "R_tau", 99.6), ("c_refine", "B0_b10/ALS", "method", "R_tau", 98.7), ("c_refine", "R1rep_b10/ALS", "method", "R_tau", 89.7),
              ("s_corr", "B0_b10/LoD2", "method", "R_tau", 98.5), ("s_corr", "B173nb_b10/ALS", "method", "R_tau", 98.2), ("s_corr", "B0_b10/LoD2", "prior", "R_tau", 11.8),
              ("s_keep", "B173nb_b10/ALS", "method", "R_tau", 58.6), ("s_keep", "B0_b10/ALS", "method", "R_tau", 75.0), ("s_keep", "B173nb_b10/ALS", "prior", "R_tau", 98.9),
              ("s_keep", "B0_b10/ALS", "prior", "R_tau", 94.4), ("s_corr", "B0_b10/LoD2", "method", "med", 5.42), ("s_corr", "B0_b10/LoD2", "mvsfuse", "med", 49.68)]


def mine(D, u, rk, key, f):
    e = D[u][rk]
    b = e["mean"][key] if rk == "method" else e["values"][e["results"][0]][key]
    if not str(b.get("status", "")).startswith("있음"):
        return None
    if f in ("R_tau", "R_0.2", "med"):
        v = b["gt"].get(f)
        return None if v is None else (v if f == "med" else 100 * v)
    if f in ("P_0.2A", "P_0.2A_vs_B"):
        v = b["res"]["A"].get("P_0.2")
        return None if v is None else 100 * v
    return None


def theirs(D3, u, rk, place, f):
    e = D3[u][DMK[rk]]
    o = e["mean"][place] if rk == "method" else e["values"][e["results"][0]][place]
    k = {"R_tau": "R_tau", "R_0.2": "R_0.2", "med": "dist", "P_0.2A": "P_0.2", "P_0.2A_vs_B": "Pb_0.2"}[f]
    v = o.get(k)
    return None if v is None else (v if f == "med" else 100 * v)


def main():
    D = jl(TAB / "a3_metrics.json")["data"]
    D3 = jl(DM / "tables/d3_metrics.json")["data"]
    V4 = jl("/repo/docs/experiments/phd/main_viscmp_v4/tables/의도_한눈에.json")
    out = dict(order=[], distance_task=[], v4=[])
    for key, u, rk, f, want in ORDER_VALS:
        v = mine(D, u, rk, key, f)
        out["order"].append(dict(cell=key, case=u, result=rk, metric=f, want=want, here=v, same=v is not None and abs(round(v, 1 if f != "med" else 2) - want) < (0.051 if f != "med" else 0.0051)))
    for key, place in MAP.items():
        for s, p in CASES:
            u = f"{s}/{p}"
            for rk in DMK:
                for f in ("R_tau", "R_0.2", "med", "P_0.2A", "P_0.2A_vs_B"):
                    a, b = mine(D, u, rk, key, f), theirs(D3, u, rk, place, f)
                    if a is None and b is None:
                        continue
                    out["distance_task"].append(dict(cell=key, place=place, case=u, result=rk, metric=f, here=a, record=b,
                                                     same=a is not None and b is not None and abs(a - b) < 1e-6, kind="비교" if key == "c_refine" else "점검"))
    pl = {"c11": "s_corr", "img": "s_keep"}
    for c in V4["cells"]:
        key = pl.get(c["place"])
        if key is None:
            continue
        rk = {"2DGS": "twodgs", "GeoGS": "geogs", "결합": "mvsfuse", "CDGS": "cdgs", "본 방법": "method"}[c["method"]]
        a = mine(D, c["case"], rk, key, "med")
        out["v4"].append(dict(cell=key, case=c["case"], result=rk, here=a, record=c["value_cm"], same=a is not None and abs(a - c["value_cm"]) < 1e-6))
        if rk == "method":
            a = mine(D, c["case"], "prior", key, "med")
            out["v4"].append(dict(cell=key, case=c["case"], result="prior", here=a, record=c["prior_cm"], same=a is not None and abs(a - c["prior_cm"]) < 1e-6))
    jdump(TAB / "a3_checks.json", dict(task="PHD-MAIN-AXES71-v2", made=now(), data=out, scientific_verdict=None))
    jdump(DOCS / "tables/일3_맞춰볼값.json", dict(task="PHD-MAIN-AXES71-v2", made=now(), data=out, scientific_verdict=None))
    MK = {"R_tau": "R(τ) %", "R_0.2": "R(0.2 m) %", "med": "참값 기준 거리의 중앙값 cm", "P_0.2A": "P(0.2 m) 셈 가 %", "P_0.2A_vs_B": "P(0.2 m) 셈 가 대 기록 셈 나 %"}
    L = ["# 일 3 맞춰 볼 값 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 본 방법 = 두 씨앗 평균.", "", "## 발주문 6절의 값", "",
         "| 칸 | 경우 | 결과 | 값 | 발주 | 여기 | 같음 |", "|---|---|---|---|---:|---:|---|"]
    from ax_common import KEY_KO
    for c in out["order"]:
        L.append(f"| {KEY_KO[c['cell']]} | {case_ko(*c['case'].split('/'))} | {RES_KO[c['result']]} | {MK[c['metric']]} | {c['want']} | {'—' if c['here'] is None else format(c['here'], '.3f')} | {'같음' if c['same'] else '어긋남 !'} |")
    n_chk = [c for c in out["distance_task"] if c["kind"] == "점검" and c["metric"] != "P_0.2A"]
    bad = [c for c in n_chk if not c["same"]]
    pa = [c for c in out["distance_task"] if c["kind"] == "점검" and c["metric"] == "P_0.2A"]
    L += ["", f"## 새 거리 지표와 같은 칸 (보정 합 = c11, 보정 · 1~4τ = c11s, 보존 합 = img)", "", f"- 점검 {len(n_chk)}칸 가운데 같음 {len(n_chk) - len(bad)}, 다름 {len(bad)} (반올림 전, 1e-6). 결과 기준 P(0.2 m)은 이 발주의 셈 가를 기록의 셈 나(대응 참값 행 없는 패치의 결과 점을 뺌)와 맞춰 봄.",
          f"- 이 발주의 칸은 대응 참값 행이 없는 패치를 '참값 없음'으로 보내므로, 다른 칸의 결과 점에는 그런 패치의 점이 없다. 그래서 칸의 셈 가 = 기록의 셈 나다. 기록의 셈 가와는 {sum(not c['same'] for c in pa)}/{len(pa)}칸이 다르다(그 패치의 결과 점이 기록의 곳에는 들고 이 발주의 칸에는 들지 않음).", ""]
    if bad:
        L += ["| 칸 | 경우 | 결과 | 값 | 기록 | 여기 |", "|---|---|---|---|---:|---:|"]
        for c in bad:
            L.append(f"| {KEY_KO[c['cell']]} | {case_ko(*c['case'].split('/'))} | {RES_KO[c['result']]} | {MK[c['metric']]} | {c['record']} | {c['here']} |")
    cmp_ = [c for c in out["distance_task"] if c["kind"] == "비교"]
    L += ["", "## 다듬기와 '두 자료가 모두 맞는 곳'(c2) — 비교 (칸이 거른 영상 오류인 코드 2 패치만큼 다름)", "", "| 경우 | 결과 | 값 | c2 기록 | 다듬기 | 차 |", "|---|---|---|---:|---:|---:|"]
    for c in cmp_:
        if c["metric"] not in ("R_tau", "med") or c["here"] is None or c["record"] is None:
            continue
        L.append(f"| {case_ko(*c['case'].split('/'))} | {RES_KO[c['result']]} | {MK[c['metric']]} | {c['record']:.3f} | {c['here']:.3f} | {c['here'] - c['record']:+.3f} |")
    bv = [c for c in out["v4"] if not c["same"]]
    L += ["", "## v4 의도 한눈에 표의 반올림 전 값 (참값 기준 거리의 중앙값)", "", f"- {len(out['v4'])}칸 가운데 같음 {len(out['v4']) - len(bv)}, 다름 {len(bv)}.", ""]
    for c in bv:
        L.append(f"- 다름: {KEY_KO[c['cell']]} {case_ko(*c['case'].split('/'))} {RES_KO[c['result']]} 기록 {c['record']} · 여기 {c['here']}")
    (DOCS / "tables/일3_맞춰볼값.md").write_text("\n".join(L) + "\n")
    print("checks", sum(c["same"] for c in out["order"]), len(out["order"]), len(bad), len(bv))


if __name__ == "__main__":
    main()
