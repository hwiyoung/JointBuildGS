"""PHD-MAIN-UNCERT-v1 최종 보고서와 숫자표 (order 9, 10) from the tables of the chosen ring radius (1.7) and the patch values.

  python u5_final.py   -> /docs/본실험_불확실도지도_보고_v1.md, /docs/불확실도지도_숫자표_v1(_k).md, /docs/tables/answers.json

The numbers sheet: the questions and answers first, then table 1 and 2 (per case, per cell), 6.1-6.5, 7.1-7.2, the places; MVS 판 가
everywhere except 6.2 and the glass places (판 나 too, order 1.2-6); one decimal, rank correlation and AUC two; '표본 부족' under 30
patches, '결과 없음' without a result, '!' where a value differs from the record by more than two times. Split at 20,000 characters.
scientific_verdict: null."""
import json
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import u3_lib as L  # noqa: E402
import u5_answers as A  # noqa: E402
import uc_common as U  # noqa: E402
from u3_lib import fmt, md_table  # noqa: E402

R, FOLDER = L.parse_R(__import__("os").environ.get("UC_R") or "chosen")
T = U.DOCS / "tables" / FOLDER
FIGR = f"figures/{FOLDER}"
S = L.Store(R)
GA = "MVS 판 가"


def jv(name):
    return json.loads((T / f"{name}.json").read_text())["values"]


# ------------------------------------------------------------------------------------------------ value answers 6, 7, 8
def q6():
    pool = {}
    for r in jv("t65_missed_edge")["missed"]:
        if r["cell"] != "전체":
            continue
        k = ("LoD2" if "LoD2" in r["case"] else "ALS", r["data"])
        a = pool.setdefault(k, [0, 0, 0.0])
        a[0] += r["patches"]; a[1] += r["missed"]; a[2] += r["missed_area_m2"]
    cells = {}
    for r in jv("t65_missed_edge")["missed"]:
        if r["cell"] in ("전체",) or r["data"] != GA or r["cell"] in [v[0] for v in U.SUMS.values()]:
            continue
        cells[r["cell"]] = cells.get(r["cell"], 0) + r["missed_area_m2"]
    top = sorted(cells.items(), key=lambda x: -x[1])[:3]
    txt = "; ".join(f"{U.PRIOR_KO[p]} 패치 {d} {100 * v[1] / max(v[0], 1):.1f} %({v[2]:.0f} m²)" for (p, d), v in pool.items() if d != "MVS 판 나")
    txt += ". 판 가의 놓친 넓이가 큰 칸: " + ", ".join(f"{c} {a:.0f} m²" for c, a in top)
    return txt, dict(pool={f"{k[0]}|{k[1]}": v for k, v in pool.items()}, cells_mvs_a_area=cells)


def q7():
    out, parts = {}, []
    eb = U.CFG["tables"]["edge_bins_m"]
    for pset, d in (("LoD2", "mvs_a"), ("ALS", "mvs_a"), ("ALS", "als")):
        z = S.pooled(pset)
        m = L.ev(z) & L.has(z, d) & np.isfinite(z[f"{d}_e"])
        r = {}
        for a, b in ((eb[0], eb[1]), (eb[3], None)):
            k = m & (z["edge"] >= a) & ((z["edge"] < b) if b is not None else True)
            r[f"{a}~{b}"] = dict(n=int(k.sum()), u=100 * float(np.median(z[f"{d}_u"][k])), e=100 * float(np.median(z[f"{d}_e"][k])))
        near, far = r[f"{eb[0]}~{eb[1]}"], r[f"{eb[3]}~None"]
        out[f"{pset}|{d}"] = r
        parts.append(f"{U.DATA_KO[d]}({U.PRIOR_KO[pset]} 패치) 0~0.5 m에서 u {near['u']:.1f}·e {near['e']:.1f} cm, 2 m 넘음에서 u {far['u']:.1f}·e {far['e']:.1f} cm")
    return "; ".join(parts), out


def q8():
    out, better, worse = {}, [], []
    for pset in U.PRIORS:
        z = S.pooled(pset)
        e = L.ev(z) & (z["gt_status"] == 0)
        for ck, cko in L.cell_keys()[1:]:
            m = e & U.cell_mask(z["cell"], ck)
            if m.sum() < 30:
                continue
            em, ep, ew = (float(np.nanmedian(z[k][m])) for k in ("errM_a", "errP", "errW_a"))
            out[f"{pset}|{cko}"] = dict(n=int(m.sum()), mvs=100 * em, prior=100 * ep, weighted=100 * ew)
            if ck in U.SUMS:
                continue
            if ew < min(em, ep) - 1e-4:
                better.append(f"{U.PRIOR_KO[pset]} {cko}")
            elif ew > min(em, ep) + 1e-4:
                worse.append(f"{U.PRIOR_KO[pset]} {cko}")
    txt = ("둘 다보다 나음: " + (", ".join(better) or "없음") + ". 나은 쪽보다 못함: " + (", ".join(worse) or "없음")
           + " (세 지역 합, 칸마다 자리의 오차 중앙값, 판 가, 30패치 넘는 칸)")
    return txt, out


def answers():
    a = {}
    a["1"] = A.q1(T)
    a["2"] = A.q2(T)
    a["3"] = A.q3(T)
    a["4"] = A.q4(T)
    a["5"] = A.q5(T)
    a["6"] = ("값으로 답함",) + q6()
    a["7"] = ("값으로 답함",) + q7()
    a["8"] = ("값으로 답함",) + q8()
    a["9"] = A.q9(T)
    return a


def ans_rows(a):
    def rho(d):
        return ", ".join(f"{U.PRIOR_KO[p]} 패치 ρ {v['rho']:.2f}, 커지지 않는 구간 {v['non_increasing']}" for p, v in d.items())
    q4 = ", ".join(f"{c} {max(v['ratio'].values()):.2f}배" for c, v in a["4"][1].items() if v.get("ratio"))
    q5 = ", ".join(f"{s} {v['q68_cm']:.1f} cm" for s, v in a["5"][1].items() if v["q68_cm"] is not None)
    q9 = "; ".join(f"{U.PRIOR_KO[p]} 패치: ρ(u/q) e {v['rank']['e']['u']:.2f}/{v['rank']['e']['q']:.2f}, 실제 68.3 % {v['rank']['qe']['u']:.2f}/{v['rank']['qe']['q']:.2f}, "
                   f"틀린 점 비율 {v['rank']['f']['u']:.2f}/{v['rank']['f']['q']:.2f}, 틀린 점으로 정한 AUC {v['auc_f']['u']:.2f}/{v['auc_f']['q']:.2f}" for p, v in a["9"][1].items())
    return [["1. MVS 불확실도가 실제 오차를 따라가는가 (판 가)", a["1"][0], rho(a["1"][1])],
            ["2. 항공 LiDAR 불확실도가 실제 오차를 따라가는가", a["2"][0], rho(a["2"][1])],
            ["3. MVS 불확실도가 영상이 틀린 패치를 잡는가 (판 가)", a["3"][0], ", ".join(f"{U.PRIOR_KO[p]} AUC {v['auc']:.2f}" for p, v in a["3"][1].items())],
            ["4. 바뀐 곳에서 MVS 불확실도가 다듬기만큼 작은가", a["4"][0], "보정 칸 u_M 중앙값 ÷ 다듬기(큰 쪽): " + q4],
            ["5. LoD2 20 cm가 자료와 맞는가", a["5"][0], "지붕면 p_G 크기의 68 % 값(보정 · 4τ 넘음 뺌): " + q5],
            ["6. 놓친 곳은 얼마나 넓은가", "값으로 답함", a["6"][1]],
            ["7. 가장자리에서 불확실도가 실제 오차보다 얼마나 커지는가", "값으로 답함", a["7"][1]],
            ["8. 무게 평균이 두 자료 각각보다 나은 칸과 못한 칸은 어디인가", "값으로 답함", a["8"][1]],
            ["9. 지금 식과 68.3 % 값 가운데 어느 쪽이 실제 오차를 더 잘 따라가는가", a["9"][0], q9]]


# ------------------------------------------------------------------------------------------------ numbers sheet
def sheet(a):
    sec = []
    sec.append("## 물음과 답\n\n" + md_table(["물음", "답", "값"], ans_rows(a), left=True))
    t1 = jv("t1_value_share")
    rows = [[r["case"], r["data"], r["face"], fmt(r["patches"], "int"), fmt(r["value"], "pct", r["patches"]), fmt(r["no_face"], "pct", r["patches"]),
             fmt(r["short"], "pct", r["patches"]), fmt(r["no_cand"], "pct", r["patches"]), fmt(r["one_sided"], "pct", r["patches"]), fmt(r["weak_final"], "pct", r["patches"])]
            for r in t1 if "face" in r and r["data"] != "MVS 판 나"]
    sec.append("## 표 1. 값이 있는 비율 (평가 범위)\n\n" + md_table(["경우", "자료", "면", "패치", "값 있음", "면 없음", "점 부족", "후보 없음", "한쪽 고리*", "지지 약함(다시 맞춘 평면)*"], rows)
               + "\n\n\\* 값이 있는 패치 가운데. 발주 글 그대로의 '지지 약함'은 늘 0.")
    rows = [[r["case"], r["data"], r["cell"], fmt(r["patches"], "int"), fmt(r["value"], "pct", r["patches"]), fmt(r["no_face"], "pct", r["patches"]),
             fmt(r["short"], "pct", r["patches"])] for r in t1 if "cell" in r and r["data"] != "MVS 판 나" and r["patches"] > 0]
    sec.append("### 표 1. 칸마다\n\n" + md_table(["경우", "자료", "칸", "패치", "값 있음", "면 없음", "점 부족"], rows))
    t2 = jv("t2_u_distribution")
    rows = [[r["case"], r["data"], r["face"], fmt(r["u"]["n"], "int")] + [fmt(r["u"][k], "v", r["u"]["n"]) for k in ("p50", "p25", "p75", "p90")]
            + [fmt(r["a"]["p50"], "v", r["u"]["n"]), fmt(r["s"]["p50"], "v", r["u"]["n"])] for r in t2 if "face" in r and r["data"] != "MVS 판 나"]
    sec.append("## 표 2. 불확실도의 분포 (cm)\n\n" + md_table(["경우", "자료", "면", "패치", "u 중앙값", "25 %", "75 %", "90 %", "어긋남 중앙값", "흩어짐 중앙값"], rows))
    rows = [[r["case"], r["data"], r["cell"], fmt(r["u"]["n"], "int"), fmt(r["u"]["p50"], "v", r["u"]["n"]), fmt(r["u"]["p75"], "v", r["u"]["n"]),
             fmt(r["a"]["p50"], "v", r["u"]["n"]), fmt(r["s"]["p50"], "v", r["u"]["n"])] for r in t2 if "cell" in r and r["data"] != "MVS 판 나" and r["u"]["n"] > 0]
    sec.append("### 표 2. 칸마다\n\n" + md_table(["경우", "자료", "칸", "패치", "u 중앙값", "u 75 %", "어긋남 중앙값", "흩어짐 중앙값"], rows))
    J = jv("t61_u_vs_error")
    rows = []
    for b in J["bins_u"]:
        if b["data"] == "MVS 판 나" or not b["unit"].startswith("세 지역"):
            continue
        for x in b["rows"]:
            rows.append([b["unit"], b["data"], x["bin"], fmt(x["n"], "int"), fmt(x["area_m2"]), fmt(x["p50"], "v", x["n"]), fmt(x["p25"], "v", x["n"]), fmt(x["p75"], "v", x["n"]),
                         fmt(x["p90"], "v", x["n"])])
    sec.append("## 6.1 u 구간별 실제 오차 e (세 지역 합, cm)\n\n" + md_table(["단위", "자료", "u 구간", "패치", "넓이 m²", "e 중앙값", "25 %", "75 %", "90 %"], rows))
    rows = []
    for r in J["rank"]:
        if r["data"] == "MVS 판 나":
            continue
        f = r["faces"]
        rows.append([r["unit"], r["data"], fmt(f["전체"]["n"], "int"), fmt(f["전체"]["rho_u_e"], "rank", f["전체"]["n"]), fmt(f["지붕꼴"]["rho_u_e"], "rank", f["지붕꼴"]["n"]),
                     fmt(f["벽꼴"]["rho_u_e"], "rank", f["벽꼴"]["n"]), fmt(f["전체"]["rho_a_bias"], "rank", f["전체"]["n"]), fmt(f["전체"]["rho_s_spread"], "rank", f["전체"]["n"]),
                     fmt(f["전체"]["med_e_over_u"], "rank", f["전체"]["n"]), fmt(f["전체"]["rho_q_e"], "rank", f["전체"]["n"])])
    sec.append("### 6.1 순위 상관\n\n" + md_table(["단위", "자료", "패치", "ρ(u,e)", "지붕꼴", "벽꼴", "ρ(어긋남, 치우침 크기)", "ρ(흩어짐, 퍼짐)", "e ÷ u 중앙값", "ρ(q,e)"], rows))
    rows = []
    for r in J["rank"]:
        if r["data"] == "MVS 판 나":
            continue
        t3 = r["u_q_vs_three"]
        n = r["faces"]["전체"]["n"]
        rows.append([r["unit"], r["data"]] + [fmt(t3[k], "rank", n) for k in ("u_e", "u_qe", "u_f", "q_e", "q_qe", "q_f")])
    sec.append("### 6.1 u와 q, 세 실제 오차의 순위 상관\n\n" + md_table(["단위", "자료", "u–e", "u–실제 68.3 %", "u–틀린 점", "q–e", "q–실제 68.3 %", "q–틀린 점"], rows))
    rows = [[h["unit"], h["data"], h["cell"], fmt(h["u"]["n"], "int"), fmt(h["u"]["area_m2"]), fmt(h["u"]["p50"], "v", h["u"]["n"]), fmt(h["u"]["p75"], "v", h["u"]["n"]),
             fmt(h["q"]["p50"], "v", h["u"]["n"]), fmt(h["q"]["p75"], "v", h["u"]["n"])] for h in J["half_wrong"] if h["data"] != "MVS 판 나" and h["u"]["n"] > 0]
    sec.append("### 6.1 반쯤 틀린 패치(틀린 점 30~50 %)\n\n" + md_table(["단위", "자료", "칸", "패치", "넓이 m²", "u 중앙값", "u 75 %", "q 중앙값", "q 75 %"], rows))
    Rr = jv("t62_roc")
    rows = [[r["unit"], r["data"], r["positives"], fmt(r["scores"]["u"]["n_pos"], "int"), fmt(r["scores"]["u"]["n_neg"], "int")]
            + [fmt(r["scores"][k]["auc"], "rank", min(r["scores"]["u"]["n_pos"], r["scores"]["u"]["n_neg"])) for k in ("u", "어긋남", "흩어짐", "q")]
            + [fmt(r["scores"]["u"]["fpr_half"], "pct", r["scores"]["u"]["n_pos"])] for r in Rr["cells"]]
    sec.append("## 6.2 영상이 틀린 패치를 잡는가 (AUC; 판 가와 판 나)\n\n" + md_table(["단위", "자료", "양성", "양성 패치", "음성 패치", "u", "어긋남", "흩어짐", "q", "절반 문턱의 잘못 잡음"], rows))
    rows = [[r["unit"], r["data"], fmt(r["scores"]["u"]["n_pos"], "int"), fmt(r["scores"]["u"]["n_neg"], "int")]
            + [fmt(r["scores"][k]["auc"], "rank", min(r["scores"]["u"]["n_pos"], r["scores"]["u"]["n_neg"])) for k in ("u", "어긋남", "흩어짐", "q")] for r in Rr["by_f"]]
    sec.append("### 6.2 틀린 점의 비율로 정한 양성(30 % 넘음)·음성(10 % 미만)\n\n" + md_table(["단위", "자료", "양성", "음성", "u", "어긋남", "흩어짐", "q"], rows))
    rows = [[r["case"], r["data"], r["cell"], fmt(r["u"]["n"], "int"), fmt(r["u"]["p50"], "v", r["u"]["n"]), fmt(r["u"]["p75"], "v", r["u"]["n"]), fmt(r["u"]["p90"], "v", r["u"]["n"]),
             fmt(r["w_over_half_area_share"], "pct", r["patches"])] for r in jv("t63_changed") if r["data"] != "MVS 판 나"]
    sec.append("## 6.3 바뀐 곳에서 MVS (cm)\n\n" + md_table(["경우", "자료", "칸", "u 있는 패치", "u_M 중앙값", "75 %", "90 %", "무게 비율 0.5 넘는 넓이"], rows))
    rows = [[r["site"], r["group"], r["basis"], fmt(r["n"], "int")] + [fmt(r.get(k), "v", r["n"]) for k in ("med_cm", "nmad_cm", "q68_cm", "q95_cm")]
            + [fmt(r.get("within20"), "pct", r["n"]), fmt(r.get("within30"), "pct", r["n"]), f"{r['tau_over_2_5_cm']:.1f}"] for r in jv("t64_lod2")]
    sec.append("## 6.4 LoD2 20 cm (cm)\n\n" + md_table(["지역", "줄", "기준", "패치", "중앙값", "NMAD", "68 %", "95 %", "20 cm 안", "30 cm 안", "τ ÷ 2.5"], rows))
    M = jv("t65_missed_edge")
    rows = [[r["case"], r["data"], r["cell"], fmt(r["patches"], "int"), fmt(r["missed"], "int"), fmt(r["missed_area_m2"]), fmt(r["share"], "pct", r["patches"])]
            for r in M["missed"] if r["data"] != "MVS 판 나" and r["patches"] > 0]
    sec.append("## 6.5 놓친 패치\n\n" + md_table(["경우", "자료", "칸", "패치", "놓친 패치", "놓친 넓이 m²", "비율"], rows))
    rows = [[r["case"], r["data"], r["flag"], r["bin"], fmt(r["u"]["n"], "int"), fmt(r["u"]["p50"], "v", r["u"]["n"]), fmt(r["e"]["p50"], "v", r["u"]["n"])]
            for r in M["edge"] if r["data"] != "MVS 판 나"]
    sec.append("### 6.5 가장자리\n\n" + md_table(["경우", "자료", "표시", "거리 (m)", "패치", "u 중앙값", "e 중앙값"], rows))
    rows = [[r["case"], r["data"], r["cell"], fmt(r["patches"], "int"), fmt(r["w_med"], "rank", r["patches"]), fmt(r["mvs_leads"], "pct", r["patches"]),
             fmt(r["prior_only"], "pct", r["patches"]), fmt(r["mvs_only"], "pct", r["patches"]), fmt(r["none"], "pct", r["patches"])] for r in jv("t71_who_leads") if r["data"] != "MVS 판 나"]
    sec.append("## 7.1 누가 이끄는가 (넓이 비율)\n\n" + md_table(["경우", "자료", "칸", "패치", "무게 비율 중앙값", "MVS가 이끎", "사전 정보만", "MVS만", "둘 다 없음"], rows))
    rows = [[r["case"], r["data"], r["cell"], fmt(r["patches"], "int")] + sum([[fmt(r[k]["med_cm"], "v", r[k]["n"]), fmt(r[k]["within20"], "pct", r[k]["n"])] for k in ("mvs", "prior", "weighted")], [])
            + [fmt(r["z"]["med"], "rank", r["z"]["n"]), fmt(r["z"]["over"], "pct", r["z"]["n"])] for r in jv("t72_weighted_preview") if r["data"] != "MVS 판 나"]
    sec.append("## 7.2 무게 평균 미리 보기 — 학습 없음, 미리 보기 (cm)\n\n" + md_table(["경우", "자료", "칸", "패치", "MVS만", "20 cm 안", "사전 정보만", "20 cm 안", "무게 평균", "20 cm 안", "z 중앙값", "z > 2.5"], rows))
    sec.append("## 자리마다의 값 (중앙값, cm)\n\n" + places_table()[0])
    rcf = U.DOCS / "tables/ring_choice.json"
    rc = json.loads(rcf.read_text())["values"] if rcf.exists() else None
    rows = [[U.SITE_KO[s], f"{R_:g}", fmt(v["per_R"][str(R_)]["rho_mvs"], "rank"), fmt(v["per_R"][str(R_)]["rho_als"], "rank"),
             fmt(v["per_R"][str(R_)]["criterion"], "rank")] for s, v in rc["per_site"].items() for R_ in U.D["ring_radii_m"]] if rc else []
    sec.append("## 1.7 고리 크기 고르기 (띠 패치)\n\n" + md_table(["지역", "R (m)", "ρ_MVS", "ρ_항공 LiDAR", "잣대"], rows) + "\n\n고른 크기: " + L.rlabel(S))
    return sec


def places_table():
    P = jv("places")
    rows, js = [], []
    checks = []
    for r in P:
        a, b = r["mvs_a"], r["mvs_b"]
        n = r["patches"]
        rows.append([r["ko"], U.PRIOR_KO[r["prior"]], fmt(n, "int"), fmt(r["area_m2"]), fmt(a["u_cm"], "v", n), fmt(r["u_prior_cm"], "v", n), fmt(a["e_cm"], "v", n),
                     fmt(r["e_prior_cm"], "v", n), fmt(a["w_med"], "rank", n), fmt(a["p_cm"], "v", n), fmt(r["p_G_cm"], "v", n), fmt(a["pW_cm"], "v", n),
                     fmt(r["gt_multi_layer_share"], "pct", n)] + ([fmt(b["u_cm"], "v", n), fmt(b["e_cm"], "v", n)] if r["place"].startswith("glass") else ["", ""]))
        ck = r.get("check")
        if ck and r["prior"] == "ALS":
            mg = a["mvs_minus_gt_cm"]
            pg = -r["p_G_cm"] if r["p_G_cm"] is not None else None

            def cmp(mine, rec):
                if mine is None or rec is None:
                    return "결과 없음"
                bad = (abs(mine) > 2 * abs(rec)) or (abs(rec) > 2 * abs(mine))
                return f"{mine:.1f} 대 기록 {rec:.1f}" + (" ! 어긋남" if bad else "")
            if "mvs_minus_gt_med_cm" in ck:
                checks.append([r["ko"], "MVS − 참값 중앙값", cmp(mg, ck["mvs_minus_gt_med_cm"]), "기록 = 참값 점마다의 MVS 깊이 − 참값(실제 사진 그림 1), 여기 = 패치마다 p_M − p_G의 중앙값"])
                checks.append([r["ko"], "MVS − 참값 NMAD", cmp(a["mvs_minus_gt_nmad_cm"], ck["mvs_minus_gt_nmad_cm"]), "같은 차이"])
                z = S.get(r["site"], r["prior"])
                idx = np.load(U.WORK / "places.npz")[f"{r['place']}__{r['prior']}"]
                na, nb = float(np.nansum(z["mvs_a_n_inner_all"][idx])), float(np.nansum(z["mvs_b_n_inner_all"][idx]))
                checks.append([r["ko"], "마스크 통과", f"판 가 점 ÷ 판 나 점 {100 * na / nb:.1f} % 대 기록 {ck['mask_pass_pct']:.1f} %" if nb > 0 else "결과 없음",
                               "정의가 다름: 기록 = 화소의 마스크 통과율, 여기 = 자리 패치 안쪽 원 점(솎기 전) 수의 비율(판 가 점이 판 나 점의 부분 집합인지는 보지 않음)"])
            if "mvs_minus_gt_cm" in ck:
                checks.append([r["ko"], "MVS − 참값", cmp(mg, ck["mvs_minus_gt_cm"]), "기록의 셈은 참값 점마다, 여기는 패치 중앙값"])
            if "gt_minus_prior_cm" in ck:
                checks.append([r["ko"], "사전 정보 − 참값", cmp(pg, ck["gt_minus_prior_cm"]), "기록 '참값에서 사전 정보'를 사전 정보 − 참값으로 읽음"])
            if "prior_minus_gt_cm" in ck:
                checks.append([r["ko"], "사전 정보 − 참값", cmp(pg, ck["prior_minus_gt_cm"]), ""])
            if "als_plane_fit_spread_cm" in ck:
                checks.append([r["ko"], "항공 LiDAR 평면 맞춤 흔들림", f"u_A 중앙값 {r['u_prior_cm']:.1f} 대 기록 {ck['als_plane_fit_spread_cm']:.2f}", "정의가 다름(기록 = 고친 판 시험 일 1의 평면 맞춤 흔들림)"])
        js.append(r)
    head = ["자리", "사전 정보", "패치", "넓이 m²", "u_M", "u_사전", "e_M", "e_사전", "무게 비율", "p_M", "p_G", "p_W", "참값 여러 층", "판 나 u_M", "판 나 e_M"]
    txt = md_table(head, rows) + "\n\n맞춰 볼 값:\n\n" + md_table(["자리", "값", "이 셈 대 기록 (cm)", "비고"], checks) + "\n\nR1 고르게 낮은 평지붕: 확인 불가(앞 작업에 R1 상자의 그런 자리가 없음)."
    return txt, checks


def split_write(sections, base):
    parts, cur = [], ""
    head = f"# 불확실도지도 숫자표 v1 (PHD-MAIN-UNCERT-v1, 고리 {L.rlabel(S)}, {U.now()})\n\n"
    for s_ in sections:
        if len(cur) + len(s_) + 2 > 19000 and cur:
            parts.append(cur)
            cur = ""
        if len(s_) > 19000:                                       # one section too long: split by rows
            lines = s_.split("\n")
            hdr = lines[:4] if lines[0].startswith("#") else lines[:2]
            chunk = ""
            for ln in lines:
                if len(chunk) + len(ln) > 18000:
                    parts.append(cur + chunk) if cur else parts.append(chunk)
                    cur = ""
                    chunk = "\n".join(hdr[-2:]) + "\n" if ln.startswith("|") else ""
                chunk += ln + "\n"
            cur += chunk + "\n"
            continue
        cur += s_ + "\n\n"
    if cur:
        parts.append(cur)
    names = []
    for i, p in enumerate(parts):
        nm = f"{base}.md" if i == 0 else f"{base}_{i + 1}.md"
        (U.DOCS / nm).write_text(head + (f"(나눔 {i + 1}/{len(parts)})\n\n" if len(parts) > 1 else "") + p)
        names.append(nm)
    return names


if __name__ == "__main__":
    a = answers()
    U.jdump(U.DOCS / "tables/answers.json", dict(R=str(R), answers={k: dict(answer=v[0], values=v[1] if len(v) > 1 else None, detail=v[2] if len(v) > 2 else None)
                                                                     for k, v in a.items()}, made=U.now(), scientific_verdict=None))
    names = split_write(sheet(a), "불확실도지도_숫자표_v1")
    U.log(names, [len((U.DOCS / n).read_text()) for n in names])
    for k, v in a.items():
        U.log(k, v[0])
