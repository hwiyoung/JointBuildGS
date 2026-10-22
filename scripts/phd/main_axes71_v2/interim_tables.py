"""PHD-MAIN-AXES71-v2 중간 보고용 요약표 (reads AX/tables/a3_metrics.json, a8_check.json): -> /docs/tables/중간_결과기준점검.md. scientific_verdict: null."""
from ax_common import CASES, DOCS, ORDER, RES_KO, TAB, case_ko, jl, now

D = jl(TAB / "a3_metrics.json")["data"]
C8 = jl(TAB / "a8_check.json")["data"]
L = ["# 전체 · 결과 기준의 점검 셈 (중간 보고용 요약) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 칸 = 결과 기준 정밀도 P(τ) (%) · 결과 기준 평균 거리 (cm) · 세지 않은 결과 점 (%). 본 방법 = 두 씨앗 평균.", "",
     "| 경우 | 결과 | 셈 가 (d_r, 모두) | 셈 다 (기대 간격 ≤ τ) | 셈 마 (법선, 옆 0.5 m) | 셈 바 (법선, 옆 1 m) |", "|---|---|---|---|---|---|"]
for s, p in CASES:
    u = f"{s}/{p}"
    for rk in ORDER:
        e = D[u][rk]
        b = e["mean"]["all"] if rk == "method" else e["values"][e["results"][0]]["all"]
        if not str(b.get("status", "")).startswith("있음"):
            continue
        cs = []
        for c in "ACEF":
            x = b["res"][c]
            cs.append("—" if x.get("P_tau") is None else f"{100 * x['P_tau']:.1f} · {x['mean']:.1f} · {100 * x['excluded_share']:.1f}")
        L.append(f"| {case_ko(s, p)} | {RES_KO[rk]} | " + " | ".join(cs) + " |")
L += ["", "## 참값 밀도 구간별 1 m 넘는 결과 점 (%) — B0 · 항공 LiDAR (셈 가 → 셈 마)", "", "| 결과 | " + " | ".join(f"밀도 {i + 1}분위" for i in range(5)) + " | 참값 행 없음 |", "|---|" + "---|" * 6]
d = C8["density"]["B0_b10/ALS"]["results"]
for rk in ORDER:
    r = d.get(rk, {})
    if "A" not in r:
        continue
    cs = [f"{100 * a['over1']:.1f} → {100 * e['over1']:.1f}" if a["over1"] is not None and e["over1"] is not None else "—" for a, e in zip(r["A"], r["E"])]
    L.append(f"| {RES_KO[rk]} | " + " | ".join(cs) + " |")
(DOCS / "tables/중간_결과기준점검.md").write_text("\n".join(L) + "\n")
print("ok")
