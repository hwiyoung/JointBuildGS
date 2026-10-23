"""PHD-MAIN-UNCERT-v1 중간 보고 (order 0.3): ring 1.5 m; questions 1-3 and 6, figures A, B (three sites), E (two glass places), the
6.1 bin table, the 6.2 AUC, the 6.5 missed share, table 1. Reads /docs/tables/R1.5/*.json, /docs/tables/u1_*.json, the logs.

  python u5_interim.py   -> /docs/중간보고_v1.md   scientific_verdict: null."""
import json
import sys

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import u5_answers as A  # noqa: E402
import uc_common as U  # noqa: E402
from u3_lib import fmt, md_table  # noqa: E402

T = U.DOCS / "tables" / "R1.5"


def jv(name, T_=T):
    return json.loads((T_ / f"{name}.json").read_text())["values"]


def main():
    a1, d1 = A.q1(T)
    a2, d2 = A.q2(T)
    a3, d3 = A.q3(T)
    m = jv("t65_missed_edge")["missed"]
    pool = {}
    for r in m:
        if r["cell"] != "전체":
            continue
        prior = "LoD2" if "LoD2" in r["case"] else "ALS"
        k = (prior, r["data"])
        a = pool.setdefault(k, [0, 0, 0.0])
        a[0] += r["patches"]; a[1] += r["missed"]; a[2] += r["missed_area_m2"]
    q6 = "; ".join(f"{U.PRIOR_KO[p]} 패치의 {d} {100 * v[1] / v[0]:.1f} %({v[1]:,}패치, {v[2]:.0f} m²)" for (p, d), v in pool.items())

    def rr(d):
        return ", ".join(f"{U.PRIOR_KO[p]} 패치 ρ {v['rho']:.2f}, 커지지 않는 구간 {v['non_increasing']}" for p, v in d.items())
    L = []
    L.append("# 불확실도 지도 — 중간 보고 (고리 1.5 m)\n")
    L.append("- 작업: PHD-MAIN-UNCERT-v1 · 발주문 v2(2026-10-23) · 학습 없음 · GPU 없음 · 브랜치 `exp/main-experiment`")
    L.append(f"- 쓴 때: {U.now()} · 설정 잠금 `configs/phd/main_uncert_v1/uncert_v1.lock.json`(sha256 4044e9b8…, 01:41), 자리 둘째 잠금 `places_v1.lock.json`(01:54)")
    L.append("- scientific_verdict: null\n")
    L.append("## 1. 물음과 답 (고리 1.5 m, 세 지역 합)\n")
    L.append(md_table(["물음", "답", "볼 값"], [
        ["1. MVS 불확실도가 실제 오차를 따라가는가 (판 가)", a1, rr(d1)],
        ["2. 항공 LiDAR 불확실도가 실제 오차를 따라가는가", a2, rr(d2)],
        ["3. MVS 불확실도가 영상이 틀린 패치를 잡는가 (판 가)", a3, ", ".join(f"{U.PRIOR_KO[p]} AUC {v['auc']:.2f}(양성 {v['n_pos']:,}, 음성 {v['n_neg']:,})" for p, v in d3.items())],
        ["6. 놓친 곳은 얼마나 넓은가", "값으로 답함", q6]]))
    L.append("\n- 등급은 발주 10절의 기준을 두 패치 묶음(세 지역 합)에 그대로 적용했다. 경우마다의 값은 아래 표와 `tables/R1.5/`에 있다.")
    L.append("- 물음 1과 2의 ρ는 u와 e의 스피어만 순위 상관, '커지지 않는 구간'은 패치 100개 이상인 u 구간에서 e 중앙값이 앞 구간보다 커지지 않은 횟수다.\n")
    # progress
    q = (U.LOG / "queue.log").read_text().splitlines()
    L.append("## 2. 어디까지 왔나\n")
    L.append("- 끝: 일 1(자료 준비, 맞춰 보기, 설정과 자리 잠금), 일 2의 고리 1.5 m(세 지역, 패치 묶음 둘, MVS 판 가·판 나, 항공 LiDAR, 참값 평면), 이 보고의 표와 그림.")
    L.append("- 도는 중: 고리 1.0 m와 3.0 m(한 번에 두 크기, 09:32 시작). 1.5 m 한 바퀴가 38분이었으므로 끝은 10시 40분 무렵으로 본다.")
    L.append("- 다음: 고리 크기 고르기(1.7, 띠 패치), 고른 크기로 일 3~5의 표와 그림 모두, 최종 보고서. 최종 보고는 13시 무렵으로 본다.\n")
    # 일 1
    c = json.loads((U.DOCS / "tables/u1_checks.json").read_text())["values"]
    L.append("## 3. 일 1 요약\n")
    L.append("- MVS 점: 학습 영상(B0 243장 등) 깊이 지도의 화소마다 한 점, 합치지 않음. 판 가 = 관측 신뢰도 마스크를 통과한 깊이(마스크 = 깊이가 있는 화소와 같음), "
             "판 나 = 마스크 전 광도 단계 깊이. 깊이는 광축 방향 깊이이고, 사전 정보 렌더 깊이를 같은 식으로 풀면 LoD2 면에서 0.03 mm 안에 놓였다(광선 거리로 읽으면 15~40 cm 벗어남).")
    L.append("- 원래 항공 LiDAR 점: P0의 LAZ 타일 넷, 분류 2와 6, 정합 이동은 영역 파일과 같다. 원래 점의 자리 p_A는 사전 정보 면에서 중앙값 0.0 cm, NMAD 0.1 cm 안이다(TIN이 그 점을 지남).")
    L.append("- 칸: 여섯 경우 모두 두 축 평가가 저장한 칸과 패치마다 같다. τ는 표 A와 같다. LoD2 벽 법선은 B173 주변 면 132(13패치)만 안쪽을 가리켜 뒤집었다.")
    L.append("- 2.8 멈춤: 항공 LiDAR 경우 다듬기 패치의 p_M 중앙값은 B0 1.1, B173 주변 8.1, R1 1.7 cm로 기준 안이었다. 영상 하나의 점으로 구한 값은 영상 사이에서 18.1, 18.7, 76.5 cm 벌어져 멈춤 조건이 걸렸다. "
             "같은 패치에서 짝지은 차의 크기는 중앙값 1.7, 2.0, 1.3 cm이고, 벗어난 영상(B0 4장, B173 주변 6장, R1 25장)은 R1에서 지붕을 멀리서 스치듯 본 비스듬한 영상이다. "
             "확인 내용을 적어 여쭈었고, 사용자 결정(10월 23일 09:31)으로 '그대로 진행'했다.")
    L.append("- 표: [tables/u1_found.md](tables/u1_found.md), [tables/u1_checks.md](tables/u1_checks.md).\n")
    # table 1 summary
    t1 = jv("t1_value_share")
    rows = [[r["case"], r["data"], fmt(r["patches"], "int"), fmt(r["value"], "pct", r["patches"]), fmt(r["no_face"], "pct", r["patches"]), fmt(r["short"], "pct", r["patches"]),
             fmt(r["one_sided"], "pct", r["patches"]), fmt(r["weak_final"], "pct", r["patches"])] for r in t1 if r.get("face") == "전체"]
    L.append("## 4. 표 1. 값이 있는 비율 (평가 범위, 모든 면)\n")
    L.append(md_table(["경우", "자료", "패치", "값 있음", "면 없음", "점 부족", "한쪽 고리*", "지지 약함(다시 맞춘 평면)*"], rows))
    L.append("\n- \\* 값이 있는 패치 가운데. 발주 글 그대로의 '지지 약함'(고른 평면의 잔차)은 만들어지는 꼴상 늘 0이라 다시 맞춘 평면의 잔차로 센 비율을 함께 적었다. 지붕꼴·벽꼴과 칸마다는 [tables/R1.5/t1_value_share.md](tables/R1.5/t1_value_share.md).\n")
    # 6.1
    J = jv("t61_u_vs_error")
    L.append("## 5. 6.1 불확실도 구간별 실제 오차 (세 지역 합, cm)\n")
    rows = []
    for unit, data in (("세 지역 합 · LoD2", "MVS 판 가"), ("세 지역 합 · 항공 LiDAR", "MVS 판 가"), ("세 지역 합 · 항공 LiDAR", "항공 LiDAR"),
                       ("세 지역 합 · LoD2", "MVS 판 나"), ("세 지역 합 · 항공 LiDAR", "MVS 판 나")):
        b = next(x for x in J["bins_u"] if x["unit"] == unit and x["data"] == data)["rows"]
        for x in b:
            rows.append([unit.replace("세 지역 합 · ", "") + " 패치", data, x["bin"], fmt(x["n"], "int"), fmt(x["area_m2"]), fmt(x["p50"], "v", x["n"]),
                         fmt(x["p25"], "v", x["n"]), fmt(x["p75"], "v", x["n"]), fmt(x["p90"], "v", x["n"])])
    L.append(md_table(["패치 묶음", "자료", "u 구간", "패치", "넓이 m²", "e 중앙값", "e 25 %", "e 75 %", "e 90 %"], rows))
    rows = []
    for r in J["rank"]:
        f = r["faces"]
        rows.append([r["unit"], r["data"], fmt(f["전체"]["n"], "int"), fmt(f["전체"]["rho_u_e"], "rank", f["전체"]["n"]), fmt(f["지붕꼴"]["rho_u_e"], "rank", f["지붕꼴"]["n"]),
                     fmt(f["벽꼴"]["rho_u_e"], "rank", f["벽꼴"]["n"]), fmt(f["전체"]["rho_a_bias"], "rank", f["전체"]["n"]), fmt(f["전체"]["rho_s_spread"], "rank", f["전체"]["n"]),
                     fmt(f["전체"]["med_e_over_u"], "rank", f["전체"]["n"])])
    L.append("\n순위 상관(경우마다):\n")
    L.append(md_table(["단위", "자료", "패치", "ρ(u, e) 전체", "지붕꼴", "벽꼴", "ρ(어긋남, 치우침 크기)", "ρ(흩어짐, 퍼짐)", "e ÷ u 중앙값"], rows))
    L.append("\n- 흩어짐과 퍼짐은 같은 안쪽 원 점의 NMAD이고 기준 평면(고리 평면, 참값 평면)만 다르다. 전체 표는 [tables/R1.5/t61_u_vs_error.md](tables/R1.5/t61_u_vs_error.md).\n")
    # 6.2
    R = jv("t62_roc")
    rows = [[r["unit"], r["data"], r["positives"], fmt(r["scores"]["u"]["n_pos"], "int"), fmt(r["scores"]["u"]["n_neg"], "int")]
            + [fmt(r["scores"][k]["auc"], "rank", min(r["scores"]["u"]["n_pos"], r["scores"]["u"]["n_neg"])) for k in ("u", "어긋남", "흩어짐", "q")]
            + [fmt(r["scores"]["u"]["fpr_half"], "pct", r["scores"]["u"]["n_pos"])] for r in R["cells"] if r["positives"] == "양성 전체"]
    L.append("## 6. 6.2 영상이 틀린 패치를 잡는가 (곡선 아래 넓이)\n")
    L.append(md_table(["단위", "자료", "양성", "양성 패치", "음성 패치", "AUC u", "AUC 어긋남", "AUC 흩어짐", "AUC q", "양성 절반 문턱의 잘못 잡음"], rows))
    L.append("\n- 양성 = 보존 · 문턱 안, 한계, 이중 오류(판 나는 보존 · 거름도), 음성 = 다듬기, 보정 두 칸. 보존 · 문턱 안만, 한계만, 틀린 점의 비율로 정한 판은 "
             "[tables/R1.5/t62_roc.md](tables/R1.5/t62_roc.md).\n")
    # 6.5
    rows = [[r["case"], r["data"], fmt(r["patches"], "int"), fmt(r["missed"], "int"), fmt(r["missed_area_m2"]), fmt(r["share"], "pct", r["patches"]),
             fmt(r["area_share"], "pct", r["patches"])] for r in m if r["cell"] == "전체"]
    L.append("## 7. 6.5 놓친 패치 (e > 20 cm 그리고 e > 2u)\n")
    L.append(md_table(["경우", "자료", "값·참값 있는 패치", "놓친 패치", "놓친 넓이 m²", "패치 비율", "넓이 비율"], rows))
    L.append("\n- 칸마다와 가장자리 구간은 [tables/R1.5/t65_missed_edge.md](tables/R1.5/t65_missed_edge.md).\n")
    # figures
    L.append("## 8. 그림\n")
    for s in U.SITES:
        fa = json.loads((U.DOCS / f"figures/R1.5/A_{s}.json").read_text())
        L.append(f"**그림 A — {U.SITE_KO[s]}.** {fa['footer']}\n\n![A {s}](figures/R1.5/A_{s}.png)\n")
        L.append("- 캡션 재료: 평가 범위를 위에서 본 정사영(북쪽 위, 0.1 m 화소, 높은 패치가 위). (가) MVS 판 가의 u를 LoD2 패치에, (나) 원래 항공 LiDAR 점의 u를 항공 LiDAR 패치에, "
                 "(다) LoD2 20 cm를 LoD2 패치에 칠함. 색 0~50 cm, 50 cm 넘음 = 점 무늬, 빗금 = 값 없음, 흰색 = 그 묶음의 패치 없음. 검은 테두리 = 5.2의 자리.\n")
    for s in U.SITES:
        fb = json.loads((U.DOCS / f"figures/R1.5/B_{s}.json").read_text())
        L.append(f"**그림 B — {U.SITE_KO[s]}.** {fb['footer']}\n\n![B {s}](figures/R1.5/B_{s}.png)\n")
    L.append("- 캡션 재료: MVS 무게 비율 w_M = u_사전² ÷ (u_M² + u_사전²). 주황 = 사전 정보가 이끎(0), 흰색에 가까움 = 0.5, 파랑 = MVS가 이끎(1), 회색 = 둘 다 값 없음. "
             "(가) MVS 판 가와 항공 LiDAR(항공 LiDAR 패치), (나) MVS 판 가와 LoD2(LoD2 패치).\n")
    for p in ("glass_strip", "glass_dome"):
        fe = json.loads((U.DOCS / f"figures/R1.5/E_{p}.json").read_text())
        L.append(f"**그림 E — {dict(glass_strip='유리 띠', glass_dome='유리 둥근 지붕')[p]}.** {fe['footer']}\n\n![E {p}](figures/R1.5/E_{p}.png)\n")
    L.append("- 캡션 재료: 위 = 자리와 둘레 2 m를 키운 지도(검은 테두리 = 자리). 아래 = 자리의 가장 큰 덩어리를 그 긴 축으로 자른 단면, 띠 폭 0.5 m, 덩어리 끝에서 2 m까지. "
             "회색 MVS 점, 검정 참값 점, 주황 사전 정보 면, 청록 = 단면선 위 패치(1 m마다 하나)의 안쪽 원 점, 점선 = 그 패치의 고리 평면, 보라 막대 = 무게 평균의 자리. (마) = 판 나.\n")
    # changes
    L.append("## 9. 바꾼 것과 확인 불가 (지금까지)\n")
    L.append("- 2.8 멈춤 → 확인 → 사용자 결정 '그대로 진행'(3절).")
    L.append("- '지지 약함'은 정의대로 늘 0이라 다시 맞춘 평면의 같은 비율을 옆 열에 둠(설정 defs.weak_support_rule, 셈 전 잠금에 적음).")
    L.append("- 그림 E의 단면: 유리 띠는 떨어진 채광창 여러 개라, 자리 전체의 긴 축 대신 가장 큰 덩어리(0.36 m로 이음)의 긴 축으로 잘랐다. 그리는 법만 바꿈(그림 json에 적음).")
    L.append("- R1 고르게 낮은 평지붕: 확인 불가. 앞 작업에 R1 상자의 그런 자리가 없다(기록된 20~30 cm 평지붕은 탐색 지역 R4·R3E).")
    L.append("- R1 계단 지붕은 항공 LiDAR 패치가 0.25 m 안에 하나도 없다(LoD2 쪽 값만). 지역마다 고른 자리는 B0 항공 LiDAR의 보정 합·보존 합, R1 항공 LiDAR의 보정 합에서 2.5 m² 넘는 한 층 덩어리가 없어 '없음'.\n")
    # times
    secs = {}
    for line in q:
        parts = line.split()
        if len(parts) >= 5 and parts[2].startswith(("u1_", "u2_")):
            secs[parts[2]] = int(parts[4].rstrip("s"))
    L.append("## 10. 걸린 시간\n")
    grp = {"MVS 점 만들기(여섯 판)": [k for k in secs if k.startswith("u1_mvs")], "항공 LiDAR·참값 점": ["u1_other"], "패치 표": ["u1_patches"],
           "참값 평면(여섯 묶음)": [k for k in secs if k.startswith("u2_gt")], "고리 1.5 m 셈(15단계)": [k for k in secs if k.endswith("R1.5")]}
    L.append(md_table(["단계", "초"], [[k, sum(secs.get(x, 0) for x in v)] for k, v in grp.items()]))
    L.append("\n- CPU 48개(nice 19), 메모리 40 GB 상한. GPU와 학습 없음.")
    (U.DOCS / "중간보고_v1.md").write_text("\n".join(L) + "\n")
    U.jdump(U.DOCS / "tables/interim_answers.json", dict(q1=[a1, d1], q2=[a2, d2], q3=[a3, d3], q6=pool and {f"{k[0]}|{k[1]}": v for k, v in pool.items()},
                                                          made=U.now(), scientific_verdict=None))
    print(a1, a2, a3)


if __name__ == "__main__":
    main()
