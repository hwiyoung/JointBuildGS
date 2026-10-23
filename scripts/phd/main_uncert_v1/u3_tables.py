"""PHD-MAIN-UNCERT-v1 일 2~5 tables (jointbuildgs:dev, CPU) from patch_values of one ring radius.

  python u3_tables.py <R> [section ...]   sections: t1 t2 t61 t62 t63 t64 t65 t71 t72 places pA (default all)
  -> /docs/tables/R<R>/<name>.md|json

Every value is over the evaluation-range patches (in_eval) unless the table says 'band'. Units cm. Samples: patches, area (m2), and where
the table gives them the inner points used. A row with fewer than 30 patches is '표본 부족'. Definitions: config 'tables'.
scientific_verdict: null."""
import sys

import numpy as np

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import u3_lib as L  # noqa: E402
import uc_common as U  # noqa: E402
from u3_lib import fmt, md_table  # noqa: E402

TC = U.CFG["tables"]
DK = U.DATA_KO


def units_of(S, pset):
    """[(label, z)] = the three cases of a prior and their pool."""
    return [(U.case_ko(s, pset), S.get(s, pset)) for s in U.SITES] + [(f"세 지역 합 · {U.PRIOR_KO[pset]}", S.pooled(pset))]


# ------------------------------------------------------------------------------------------------ 표 1, 표 2
def t1(S, out):
    rows, js, rows_c = [], [], []
    head = ["경우", "자료", "면", "패치", "넓이 m²", "값 있음", "면 없음", "점 부족", "후보 없음", "한쪽 고리*", "지지 약함*", "지지 약함(다시 맞춘 평면)*", "솎음*"]
    for s, p in U.CASES:
        z = S.get(s, p)
        e = L.ev(z)
        for d in L.DATAS[p]:
            st = z[f"{d}_status"]
            for fname, fm in L.face_masks(z):
                m = e & fm
                n = int(m.sum())
                hv = m & (st == 0)
                nv = max(int(hv.sum()), 1)
                r = dict(case=U.case_ko(s, p), data=DK[d], face=fname, patches=n, area_m2=float(z["area"][m].sum()),
                         value=float((st[m] == 0).mean()) if n else None, no_face=float((st[m] == 1).mean()) if n else None,
                         short=float((st[m] == 2).mean()) if n else None, no_cand=float((st[m] == 3).mean()) if n else None,
                         one_sided=float((z[f"{d}_quadrants"][hv] < 3).sum() / nv), weak=float((z[f"{d}_support_lmeds"][hv] < 0.5).sum() / nv),
                         weak_final=float((z[f"{d}_support_final"][hv] < 0.5).sum() / nv),
                         thinned=float(((z[f"{d}_thinned_inner"][hv] == 1) | (z[f"{d}_thinned_ring"][hv] == 1)).sum() / nv) if d != "als" else None,
                         inner_points=int(np.nansum(z[f"{d}_n_inner"][hv])))
                js.append(r)
                rows.append([r["case"], r["data"], fname, fmt(n, "int"), fmt(r["area_m2"]), fmt(r["value"], "pct", n), fmt(r["no_face"], "pct", n),
                             fmt(r["short"], "pct", n), fmt(r["no_cand"], "pct", n), fmt(r["one_sided"], "pct", nv), fmt(r["weak"], "pct", nv),
                             fmt(r["weak_final"], "pct", nv), "해당 없음" if r["thinned"] is None else fmt(r["thinned"], "pct", nv)])
            for ck, cko in L.cell_keys()[1:]:
                m = e & U.cell_mask(z["cell"], ck)
                n = int(m.sum())
                rows_c.append([U.case_ko(s, p), DK[d], cko, fmt(n, "int"), fmt(float(z["area"][m].sum())),
                               fmt(float((st[m] == 0).mean()) if n else None, "pct", n), fmt(float((st[m] == 1).mean()) if n else None, "pct", n),
                               fmt(float((st[m] == 2).mean()) if n else None, "pct", n)])
                js.append(dict(case=U.case_ko(s, p), data=DK[d], cell=cko, patches=n, area_m2=float(z["area"][m].sum()),
                               value=float((st[m] == 0).mean()) if n else None, no_face=float((st[m] == 1).mean()) if n else None,
                               short=float((st[m] == 2).mean()) if n else None))
    note = ("평가 범위 안의 패치. 비율의 분모 = 그 줄의 패치(값 있음·면 없음·점 부족·후보 없음), * = 값이 있는 패치. "
            "'지지 약함'은 발주 1.2-5 글 그대로(고른 평면의 잔차)라 만들어지는 꼴상 늘 0이다(설정 defs.weak_support_rule). "
            "옆 열은 다시 맞춘 최소 제곱 평면의 잔차로 같은 비율을 센 값이다. 솎음 = 안쪽 원 2,000점 또는 고리 8,000점을 넘어 솎은 패치.")
    body = md_table(head, rows) + "\n\n## 칸마다\n\n" + md_table(["경우", "자료", "칸", "패치", "넓이 m²", "값 있음", "면 없음", "점 부족"], rows_c)
    L.write(out, "t1_value_share", f"표 1. 값이 있는 비율 (고리 {S.R} m)", body, js, note)


def t2(S, out):
    head = ["경우", "자료", "면", "패치", "넓이 m²", "안쪽 원 점", "u 중앙값", "u 25 %", "u 75 %", "u 90 %", "어긋남 중앙값", "어긋남 75 %", "어긋남 90 %",
            "흩어짐 중앙값", "흩어짐 75 %", "흩어짐 90 %", "q 중앙값", "q 90 %"]
    rows, rows_c, js = [], [], []
    for s, p in U.CASES:
        z = S.get(s, p)
        e = L.ev(z)
        for d in L.DATAS[p]:
            u, a, sd, qq = (L.val(z, d, f) for f in ("u", "a", "s", "q"))
            for fname, fm in L.face_masks(z):
                m = e & fm & L.has(z, d)
                du, da, ds, dq = (L.dist(x, z["area"], m) for x in (u, a, sd, qq))
                n = du["n"]
                r = dict(case=U.case_ko(s, p), data=DK[d], face=fname, u=du, a=da, s=ds, q=dq, inner_points=int(np.nansum(z[f"{d}_n_inner"][m])))
                js.append(r)
                rows.append([r["case"], DK[d], fname, fmt(n, "int"), fmt(du["area_m2"]), fmt(r["inner_points"], "int")]
                            + [fmt(du[k], "v", n) for k in ("p50", "p25", "p75", "p90")] + [fmt(da[k], "v", n) for k in ("p50", "p75", "p90")]
                            + [fmt(ds[k], "v", n) for k in ("p50", "p75", "p90")] + [fmt(dq[k], "v", n) for k in ("p50", "p90")])
            for ck, cko in L.cell_keys()[1:]:
                m = e & U.cell_mask(z["cell"], ck) & L.has(z, d)
                du, da, ds = (L.dist(x, z["area"], m) for x in (u, a, sd))
                n = du["n"]
                js.append(dict(case=U.case_ko(s, p), data=DK[d], cell=cko, u=du, a=da, s=ds))
                rows_c.append([U.case_ko(s, p), DK[d], cko, fmt(n, "int"), fmt(du["area_m2"])] + [fmt(du[k], "v", n) for k in ("p50", "p25", "p75", "p90")]
                              + [fmt(da["p50"], "v", n), fmt(ds["p50"], "v", n)])
    body = md_table(head, rows) + "\n\n## 칸마다\n\n" + md_table(["경우", "자료", "칸", "패치", "넓이 m²", "u 중앙값", "u 25 %", "u 75 %", "u 90 %", "어긋남 중앙값",
                                                                    "흩어짐 중앙값"], rows_c)
    L.write(out, "t2_u_distribution", f"표 2. 불확실도의 분포 (cm, 고리 {S.R} m)", body, js, "평가 범위 안, 값이 있는 패치.")


# ------------------------------------------------------------------------------------------------ 6.1
def bins_rows(score, err, area, m, edges):
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = m & (score * 100 >= lo) & ((score * 100 < hi) if hi is not None else True)
        d = L.dist(err, area, k)
        out.append(dict(bin=f"{lo}~{hi}" if hi is not None else f"{lo} 넘음", **d))
    return out


def t61(S, out):
    edges = TC["u_bins_cm"]
    head = ["단위", "자료", "u 구간 (cm)", "패치", "넓이 m²", "e 중앙값", "e 25 %", "e 75 %", "e 90 %"]
    rows, rows_q, rows_r, rows_rel, rows_half, js = [], [], [], [], [], {}
    for p in U.PRIORS:
        for lab, z in units_of(S, p):
            e = L.ev(z)
            for d in L.DATAS[p]:
                u, qq, a, sd = (L.val(z, d, f) for f in ("u", "q", "a", "s"))
                ee = z[f"{d}_e"].astype(np.float64)
                qe = z[f"{d}_qe"].astype(np.float64)
                ff = z[f"{d}_f"].astype(np.float64)
                bias = np.abs(z[f"{d}_e_bias"].astype(np.float64))
                spr = z[f"{d}_e_spread"].astype(np.float64)
                m = e & L.has(z, d) & np.isfinite(ee)
                br = bins_rows(u, ee, z["area"], m, edges)
                bq = bins_rows(qq, qe, z["area"], m, edges)
                for b in br:
                    rows.append([lab, DK[d], b["bin"], fmt(b["n"], "int"), fmt(b["area_m2"])] + [fmt(b[k], "v", b["n"]) for k in ("p50", "p25", "p75", "p90")])
                for b in bq:
                    rows_q.append([lab, DK[d], b["bin"], fmt(b["n"], "int"), fmt(b["area_m2"])] + [fmt(b[k], "v", b["n"]) for k in ("p50", "p25", "p75", "p90")])
                rec = {}
                for fname, fm in L.face_masks(z):
                    mm = m & fm
                    rho, n = L.spearman(u[mm], ee[mm])
                    ra, _ = L.spearman(a[mm], bias[mm])
                    rs, _ = L.spearman(sd[mm], spr[mm])
                    rq, _ = L.spearman(qq[mm], ee[mm])
                    with np.errstate(divide="ignore", invalid="ignore"):
                        ratio = L.med(ee[mm] / u[mm])
                    rec[fname] = dict(n=n, area_m2=float(z["area"][mm].sum()), rho_u_e=rho, rho_a_bias=ra, rho_s_spread=rs, rho_q_e=rq, med_e_over_u=ratio)
                    rows_r.append([lab, DK[d], fname, fmt(n, "int"), fmt(rec[fname]["area_m2"]), fmt(rho, "rank", n), fmt(ra, "rank", n), fmt(rs, "rank", n),
                                   fmt(ratio, "rank", n)])
                rel = {}
                for sc_name, sc in (("u", u), ("q", qq)):
                    for er_name, er in (("e", ee), ("qe", qe), ("f", ff)):
                        rel[f"{sc_name}_{er_name}"] = L.spearman(sc[m], er[m])[0]
                rows_rel.append([lab, DK[d], fmt(int(m.sum()), "int")] + [fmt(rel[k], "rank", int(m.sum())) for k in
                                                                          ("u_e", "u_qe", "u_f", "q_e", "q_qe", "q_f")])
                for ck, cko in [("all", "전체")] + [(c, U.CELL_KO[c]) for c in U.CELLS]:
                    hm = m & (ff >= TC["half_wrong_f"][0]) & (ff <= TC["half_wrong_f"][1]) & (U.cell_mask(z["cell"], ck) if ck != "all" else True)
                    du, dq = L.dist(u, z["area"], hm), L.dist(qq, z["area"], hm)
                    if ck == "all" or du["n"]:
                        rows_half.append([lab, DK[d], cko, fmt(du["n"], "int"), fmt(du["area_m2"]), fmt(du["p50"], "v", du["n"]), fmt(du["p75"], "v", du["n"]),
                                          fmt(dq["p50"], "v", du["n"]), fmt(dq["p75"], "v", du["n"])])
                    js.setdefault("half_wrong", []).append(dict(unit=lab, data=DK[d], cell=cko, u=du, q=dq))
                js.setdefault("bins_u", []).append(dict(unit=lab, data=DK[d], rows=br))
                js.setdefault("bins_q", []).append(dict(unit=lab, data=DK[d], rows=bq))
                js.setdefault("rank", []).append(dict(unit=lab, data=DK[d], faces=rec, u_q_vs_three=rel))
    body = (md_table(head, rows) + "\n\n## 순위 상관과 e ÷ u\n\n"
            + md_table(["단위", "자료", "면", "패치", "넓이 m²", "ρ(u, e)", "ρ(어긋남, 치우침 크기)", "ρ(흩어짐, 퍼짐)", "e ÷ u 중앙값"], rows_r)
            + "\n\n## 68.3 % 값 q의 구간별 실제 오차의 68.3 % 값\n\n" + md_table(head[:2] + ["q 구간 (cm)"] + head[3:5] + ["실제 68.3 % 중앙값", "25 %", "75 %", "90 %"], rows_q)
            + "\n\n## u와 q, 세 실제 오차의 순위 상관\n\n" + md_table(["단위", "자료", "패치", "u–e", "u–실제 68.3 %", "u–틀린 점 비율", "q–e", "q–실제 68.3 %", "q–틀린 점 비율"], rows_rel)
            + "\n\n## 반쯤 틀린 패치(틀린 점 비율 30~50 %)의 u와 q\n\n" + md_table(["단위", "자료", "칸", "패치", "넓이 m²", "u 중앙값", "u 75 %", "q 중앙값", "q 75 %"], rows_half))
    L.write(out, "t61_u_vs_error", f"6.1 불확실도가 실제 오차를 따라가는가 (cm, 고리 {S.R} m)", body, js,
            "평가 범위 안, 그 자료의 값과 참값 평면이 있는 패치. e = 실제 오차(1.5). 반쯤 틀린 패치의 칸 줄은 패치가 있는 칸만 적었다.")


# ------------------------------------------------------------------------------------------------ 6.2
def roc_sets(z, d):
    c = z["cell"]
    pos_cells = TC["roc_positive_cells"] + (TC["roc_positive_cells_b_extra"] if d == "mvs_b" else [])
    gt = z["gt_status"] == 0
    pos = np.isin(c, [U.CID[k] for k in pos_cells]) & gt
    neg = np.isin(c, [U.CID[k] for k in TC["roc_negative_cells"]]) & gt
    return pos, neg


def t62(S, out):
    rows, rows_f, js = [], [], {}
    for p in U.PRIORS:
        for lab, z in units_of(S, p):
            e = L.ev(z)
            for d in ("mvs_a", "mvs_b"):
                pos, neg = roc_sets(z, d)
                pos, neg = pos & e, neg & e
                for sub, pm in (("양성 전체", pos), ("보존 · 문턱 안만", pos & (z["cell"] == U.CID["c_keep_in"])), ("한계만", pos & (z["cell"] == U.CID["c_limit"]))):
                    rr = {}
                    for sn, f in (("u", "u"), ("어긋남", "a"), ("흩어짐", "s"), ("q", "q")):
                        rr[sn] = L.auc(L.val(z, d, f), pm, neg)
                    js.setdefault("cells", []).append(dict(unit=lab, data=DK[d], positives=sub, scores=rr))
                    n = min(rr["u"]["n_pos"], rr["u"]["n_neg"])
                    rows.append([lab, DK[d], sub, fmt(rr["u"]["n_pos"], "int"), fmt(rr["u"]["n_neg"], "int")]
                                + [fmt(rr[k]["auc"], "rank", n) for k in ("u", "어긋남", "흩어짐", "q")]
                                + [fmt(rr["u"]["fpr_half"], "pct", n), fmt(rr["u"]["thr_half_cm"], "v", n)])
                    if sub == "양성 전체":
                        js.setdefault("curves", []).append(dict(unit=lab, data=DK[d], curves={k: L.roc_curve(L.val(z, d, f), pm, neg)
                                                                                             for k, f in (("u", "u"), ("어긋남", "a"), ("흩어짐", "s"), ("q", "q"))}))
                ff = z[f"{d}_f"].astype(np.float64)
                base = e & (z["gt_status"] == 0) & (z["cell"] >= 0) & ~np.isin(z["cell"], [U.CID[k] for k in ("c_inh_miss", "c_miss_wrong", "c_inh_invis",
                                                                                                                 "c_invis_wrong", "c_nogt")])
                fpos, fneg = base & (ff > 0.3), base & (ff < 0.1)
                rr = {sn: L.auc(L.val(z, d, f), fpos, fneg) for sn, f in (("u", "u"), ("어긋남", "a"), ("흩어짐", "s"), ("q", "q"))}
                js.setdefault("by_f", []).append(dict(unit=lab, data=DK[d], scores=rr))
                n = min(rr["u"]["n_pos"], rr["u"]["n_neg"])
                rows_f.append([lab, DK[d], fmt(rr["u"]["n_pos"], "int"), fmt(rr["u"]["n_neg"], "int")] + [fmt(rr[k]["auc"], "rank", n) for k in ("u", "어긋남", "흩어짐", "q")]
                              + [fmt(rr["u"]["fpr_half"], "pct", n)])
    head = ["단위", "자료", "양성", "양성 패치", "음성 패치", "AUC u", "AUC 어긋남", "AUC 흩어짐", "AUC q", "양성 절반 문턱의 잘못 잡음(u)", "그 문턱 u (cm)"]
    body = (md_table(head, rows) + "\n\n## 틀린 점의 비율로 정한 양성(30 % 넘음)과 음성(10 % 미만)\n\n"
            + md_table(["단위", "자료", "양성 패치", "음성 패치", "AUC u", "AUC 어긋남", "AUC 흩어짐", "AUC q", "양성 절반 문턱의 잘못 잡음(u)"], rows_f))
    L.write(out, "t62_roc", f"6.2 MVS 불확실도가 영상이 틀린 패치를 잡는가 (고리 {S.R} m)", body, js,
            "양성 = 보존 · 문턱 안, 한계, 이중 오류(판 나는 보존 · 거름도), 음성 = 다듬기, 보정 두 칸. 평가 범위 안, 참값 평면이 있는 패치. "
            "값이 없는 패치는 뺐다(json에 뺀 수). AUC = 맨-휘트니.")


# ------------------------------------------------------------------------------------------------ 6.3
def t63(S, out):
    rows, js = [], []
    wing = np.load(U.WORK / "places.npz")
    for s, p in U.CASES:
        z = S.get(s, p)
        e = L.ev(z)
        for d, v in (("mvs_a", "a"), ("mvs_b", "b")):
            u = L.val(z, d, "u")
            w = z[f"w_{v}"]
            sets = [(U.CELL_KO[c], e & (z["cell"] == U.CID[c])) for c in ("c_corr14", "c_corr4p", "c_refine")]
            if s == "B173nb_b10":
                k = f"b173_wing__{p}"
                mm = np.zeros(len(e), bool)
                mm[wing[k]] = True
                sets.append(("B173 날개 자리", mm & e))
            for nm, m in sets:
                du = L.dist(u, z["area"], m)
                wm = m & np.isfinite(w)
                ar = z["area"][wm].sum()
                share = float(z["area"][wm & (w > 0.5)].sum() / ar) if ar > 0 else None
                r = dict(case=U.case_ko(s, p), data=DK[d], cell=nm, u=du, patches=int(m.sum()), area_m2=float(z["area"][m].sum()), w_over_half_area_share=share)
                js.append(r)
                rows.append([r["case"], DK[d], nm, fmt(r["patches"], "int"), fmt(r["area_m2"]), fmt(du["n"], "int"), fmt(du["p50"], "v", du["n"]),
                             fmt(du["p75"], "v", du["n"]), fmt(du["p90"], "v", du["n"]), fmt(share, "pct", int(wm.sum()))])
    head = ["경우", "자료", "칸", "패치", "넓이 m²", "u 있는 패치", "u_M 중앙값", "u_M 75 %", "u_M 90 %", "MVS 무게 비율 0.5 넘는 넓이 비율"]
    L.write(out, "t63_changed", f"6.3 바뀐 곳에서 MVS는 어떤가 (cm, 고리 {S.R} m)", md_table(head, rows), js,
            "평가 범위 안. 무게 비율의 넓이 비율 = 무게 비율이 정해진 패치(한 자료만 값이 있으면 0 또는 1) 넓이 가운데 0.5 넘는 넓이.")


# ------------------------------------------------------------------------------------------------ 6.4
def lod2_stats(x, m, area):
    v = np.abs(x[m & np.isfinite(x)])
    n = int(len(v))
    if not n:
        return dict(n=0)
    xx = x[m & np.isfinite(x)]
    return dict(n=n, area_m2=float(area[m & np.isfinite(x)].sum()), med_cm=100 * float(np.median(xx)), nmad_cm=100 * L.nmad(xx),
                q68_cm=100 * float(np.quantile(v, .68)), q95_cm=100 * float(np.quantile(v, .95)), within20=float(np.mean(v <= .2)), within30=float(np.mean(v <= .3)))


def t64(S, out):
    rows, js = [], []
    head = ["지역", "줄", "기준", "패치", "넓이 m²", "중앙값", "NMAD", "차 크기 68 %", "차 크기 95 %", "20 cm 안", "30 cm 안", "τ ÷ 2.5"]
    for s in U.SITES:
        z = S.get(s, "LoD2")
        e = L.ev(z)
        pM = L.val(z, "mvs_a", "p")
        uM = L.val(z, "mvs_a", "u")
        pG = np.where(z["gt_status"] == 0, z["gt_p"], np.nan).astype(np.float64)
        tau = U.CFG["cells"]["tau_cm"][s]
        groups = [("지붕면", z["roof_like"].astype(bool), tau["roof"] / 2.5), ("벽면", ~z["roof_like"].astype(bool), tau["wall"] / 2.5)]
        for rt in sorted(set(z["roof_type"][e & z["roof_like"].astype(bool)].tolist())):
            if rt:
                groups.append((f"지붕 형태 {rt} {U.CFG['patch']['roof_type_ko'].get(rt, '')}", z["roof_like"].astype(bool) & (z["roof_type"] == rt), tau["roof"] / 2.5))
        for gname, gm, t25 in groups:
            for bname, x, m in ((f"MVS(u_M ≤ {TC['trusted_mvs_cm'][0]} cm)", pM, e & gm & (uM <= TC["trusted_mvs_cm"][0] / 100)),
                                (f"MVS(u_M ≤ {TC['trusted_mvs_cm'][1]} cm)", pM, e & gm & (uM <= TC["trusted_mvs_cm"][1] / 100)),
                                ("참값(모두)", pG, e & gm), ("참값(보정 · 4τ 넘음 뺌)", pG, e & gm & (z["cell"] != U.CID["c_corr4p"]))):
                st = lod2_stats(x, m, z["area"])
                n = st["n"]
                js.append(dict(site=U.SITE_KO[s], group=gname, basis=bname, tau_over_2_5_cm=t25, **st))
                rows.append([U.SITE_KO[s], gname, bname, fmt(n, "int"), fmt(st.get("area_m2"))] + [fmt(st.get(k), "v", n) for k in ("med_cm", "nmad_cm", "q68_cm", "q95_cm")]
                            + [fmt(st.get("within20"), "pct", n), fmt(st.get("within30"), "pct", n), f"{t25:.1f}"])
    L.write(out, "t64_lod2", f"6.4 LoD2 20 cm는 자료와 맞는가 (cm, 고리 {S.R} m)", md_table(head, rows), js,
            "평가 범위 안 LoD2 패치. MVS 줄 = p_M(MVS 판 가 안쪽 원 점의 법선 거리 중앙값, LoD2 면이 0), 참값 줄 = p_G. 지붕 형태 줄은 지붕꼴 패치.")


# ------------------------------------------------------------------------------------------------ 6.5
def t65(S, out):
    rows, rows_e, js = [], [], {}
    eb = TC["edge_bins_m"]
    for s, p in U.CASES:
        z = S.get(s, p)
        e = L.ev(z)
        for d in L.DATAS[p]:
            u = L.val(z, d, "u")
            ee = z[f"{d}_e"].astype(np.float64)
            m = e & L.has(z, d) & np.isfinite(ee)
            miss = m & (ee > 0.2) & (ee > 2 * u)
            for ck, cko in L.cell_keys():
                cm = m & (U.cell_mask(z["cell"], ck) if ck != "all" else True)
                n = int(cm.sum())
                k = miss & cm
                r = dict(case=U.case_ko(s, p), data=DK[d], cell=cko, patches=n, missed=int(k.sum()), missed_area_m2=float(z["area"][k].sum()),
                         share=float(k.sum() / n) if n else None, area_share=float(z["area"][k].sum() / z["area"][cm].sum()) if n else None)
                js.setdefault("missed", []).append(r)
                if ck == "all" or n:
                    rows.append([r["case"], DK[d], cko, fmt(n, "int"), fmt(r["missed"], "int"), fmt(r["missed_area_m2"]), fmt(r["share"], "pct", n),
                                 fmt(r["area_share"], "pct", n)])
            for flag, fm in (("모든 값", np.ones(len(e), bool)), ("한쪽 고리", z[f"{d}_quadrants"] < 3), ("지지 약함(다시 맞춘 평면)", z[f"{d}_support_final"] < 0.5)):
                for lo, hi in zip(eb[:-1], eb[1:]):
                    k = m & fm & (z["edge"] >= lo) & ((z["edge"] < hi) if hi is not None else True)
                    du, de = L.dist(u, z["area"], k), L.dist(ee, z["area"], k)
                    b = f"{lo}~{hi}" if hi is not None else f"{lo} 넘음"
                    js.setdefault("edge", []).append(dict(case=U.case_ko(s, p), data=DK[d], flag=flag, bin=b, u=du, e=de))
                    rows_e.append([U.case_ko(s, p), DK[d], flag, b, fmt(du["n"], "int"), fmt(du["p50"], "v", du["n"]), fmt(de["p50"], "v", du["n"]),
                                   fmt((du["p50"] - de["p50"]) if du["n"] else None, "v", du["n"])])
    body = (md_table(["경우", "자료", "칸", "값·참값 있는 패치", "놓친 패치", "놓친 넓이 m²", "패치 비율", "넓이 비율"], rows)
            + "\n\n## 가장자리 거리 구간별 u와 e\n\n" + md_table(["경우", "자료", "패치", "가장자리 거리 (m)", "패치 수", "u 중앙값", "e 중앙값", "u − e"], rows_e))
    L.write(out, "t65_missed_edge", f"6.5 놓친 곳과 가장자리 (cm, 고리 {S.R} m)", body, js,
            "놓친 패치 = e > 20 cm 그리고 e > 2u. 가장자리 거리 = 다른 면 번호의 패치 중심까지(2 m까지). 칸 줄은 패치가 있는 칸만.")


# ------------------------------------------------------------------------------------------------ 7.1, 7.2
def t71(S, out):
    rows, js = [], []
    for s, p in U.CASES:
        z = S.get(s, p)
        e = L.ev(z)
        for v in ("a", "b"):
            w = z[f"w_{v}"]
            hM = z[f"mvs_{v}_status"] == 0
            hP = np.isfinite(z["u_prior"])
            for ck, cko in L.cell_keys():
                m = e & (U.cell_mask(z["cell"], ck) if ck != "all" else True)
                ar = z["area"][m].sum()
                n = int(m.sum())
                if not n:
                    continue
                f = lambda k: float(z["area"][k].sum() / ar) if ar > 0 else None  # noqa: E731
                r = dict(case=U.case_ko(s, p), data=DK[f"mvs_{v}"], cell=cko, patches=n, area_m2=float(ar), w_med=L.med(w[m]),
                         mvs_leads=f(m & np.isfinite(w) & (w > 0.5)), prior_only=f(m & ~hM & hP), mvs_only=f(m & hM & ~hP), none=f(m & ~hM & ~hP))
                js.append(r)
                rows.append([r["case"], r["data"], cko, fmt(n, "int"), fmt(r["area_m2"]), fmt(r["w_med"], "rank", n), fmt(r["mvs_leads"], "pct", n),
                             fmt(r["prior_only"], "pct", n), fmt(r["mvs_only"], "pct", n), fmt(r["none"], "pct", n)])
    head = ["경우", "자료", "칸", "패치", "넓이 m²", "MVS 무게 비율 중앙값", "MVS가 이끎(0.5 넘음)", "사전 정보만 값", "MVS만 값", "둘 다 없음"]
    L.write(out, "t71_who_leads", f"7.1 누가 이끄는가 (고리 {S.R} m)", md_table(head, rows), js, "평가 범위 안. 비율은 넓이 비율. 칸 줄은 패치가 있는 칸만.")


def t72(S, out):
    rows, js = [], []
    for s, p in U.CASES:
        z = S.get(s, p)
        e = L.ev(z)
        for v in ("a", "b"):
            for ck, cko in L.cell_keys():
                m = e & (U.cell_mask(z["cell"], ck) if ck != "all" else True) & (z["gt_status"] == 0)
                n = int(m.sum())
                if not n:
                    continue
                r = dict(case=U.case_ko(s, p), data=DK[f"mvs_{v}"], cell=cko, patches=n, area_m2=float(z["area"][m].sum()))
                for nm, k in (("mvs", f"errM_{v}"), ("prior", "errP"), ("weighted", f"errW_{v}")):
                    x = z[k][m]
                    x = x[np.isfinite(x)]
                    r[nm] = dict(n=int(len(x)), med_cm=100 * float(np.median(x)) if len(x) else None, within20=float(np.mean(x <= .2)) if len(x) else None)
                zz = z[f"z_{v}"][m]
                zz = zz[np.isfinite(zz)]
                r["z"] = dict(n=int(len(zz)), med=float(np.median(zz)) if len(zz) else None, over=float(np.mean(zz > TC["z_over"])) if len(zz) else None)
                js.append(r)
                rows.append([r["case"], r["data"], cko, fmt(n, "int"), fmt(r["area_m2"])]
                            + sum([[fmt(r[k]["med_cm"], "v", r[k]["n"]), fmt(r[k]["within20"], "pct", r[k]["n"])] for k in ("mvs", "prior", "weighted")], [])
                            + [fmt(r["z"]["med"], "rank", r["z"]["n"]), fmt(r["z"]["over"], "pct", r["z"]["n"])])
    head = ["경우", "자료", "칸", "패치", "넓이 m²", "MVS만 중앙값", "MVS만 20 cm 안", "사전 정보만 중앙값", "사전 정보만 20 cm 안", "무게 평균 중앙값", "무게 평균 20 cm 안",
            "z 중앙값", "z > 2.5"]
    L.write(out, "t72_weighted_preview", f"7.2 무게 평균 미리 보기 — 학습 없음, 미리 보기 (cm, 고리 {S.R} m)", md_table(head, rows), js,
            "평가 범위 안, 참값 평면이 있는 패치. 자리의 오차 = |p − p_G|(사전 정보의 자리 0). 칸 줄은 패치가 있는 칸만.")


# ------------------------------------------------------------------------------------------------ places
def place_values(S, name, site, prior, idx):
    z = S.get(site, prior)
    m = np.zeros(len(z["centre"]), bool)
    m[idx] = True
    r = dict(place=name, site=site, prior=prior, patches=int(m.sum()), area_m2=float(z["area"][m].sum()), in_eval=int((m & L.ev(z)).sum()),
             gt_multi_layer_share=float((z["gt_runs"][m] >= 2).mean()) if m.any() else None)
    for v in ("a", "b"):
        d = f"mvs_{v}"
        r[d] = dict(value_share=float((z[f"{d}_status"][m] == 0).mean()) if m.any() else None,
                    **{k: (100 * L.med(L.val(z, d, f)[m]) if L.med(L.val(z, d, f)[m]) is not None else None) for k, f in
                       (("u_cm", "u"), ("a_cm", "a"), ("s_cm", "s"), ("q_cm", "q"), ("p_cm", "p"))},
                    e_cm=100 * L.med(z[f"{d}_e"][m]) if L.med(z[f"{d}_e"][m]) is not None else None,
                    f_med=L.med(z[f"{d}_f"][m]), w_med=L.med(z[f"w_{v}"][m]),
                    pW_cm=100 * L.med(z[f"pW_{v}"][m]) if L.med(z[f"pW_{v}"][m]) is not None else None,
                    mvs_minus_gt_cm=100 * L.med((L.val(z, d, "p") - np.where(z["gt_status"] == 0, z["gt_p"], np.nan))[m])
                    if L.med((L.val(z, d, "p") - np.where(z["gt_status"] == 0, z["gt_p"], np.nan))[m]) is not None else None,
                    mvs_minus_gt_nmad_cm=(100 * L.nmad((L.val(z, d, "p") - np.where(z["gt_status"] == 0, z["gt_p"], np.nan))[m])
                                          if L.nmad((L.val(z, d, "p") - np.where(z["gt_status"] == 0, z["gt_p"], np.nan))[m]) is not None else None))
    r["u_prior_cm"] = 100 * L.med(z["u_prior"][m]) if L.med(z["u_prior"][m]) is not None else None
    r["prior_value_share"] = float(np.isfinite(z["u_prior"][m]).mean()) if m.any() else None
    pG = np.where(z["gt_status"] == 0, z["gt_p"], np.nan)
    r["p_G_cm"] = 100 * L.med(pG[m]) if L.med(pG[m]) is not None else None
    r["gt_plane_share"] = float((z["gt_status"][m] == 0).mean()) if m.any() else None
    if prior == "ALS":
        r["e_prior_cm"] = 100 * L.med(z["als_e"][m]) if L.med(z["als_e"][m]) is not None else None
        r["als_p_cm"] = 100 * L.med(L.val(z, "als", "p")[m]) if L.med(L.val(z, "als", "p")[m]) is not None else None
    else:
        r["e_prior_cm"] = 100 * L.med(np.abs(pG[m])) if L.med(np.abs(pG[m])) is not None else None
    return r


def places(S, out):
    pl = U.jl(U.WORK / "places.json")["places"]
    arr = np.load(U.WORK / "places.npz")
    rows, js = [], []
    for name in sorted({k.split("__")[0] for k in arr.files}):
        for prior in U.PRIORS:
            k = f"{name}__{prior}"
            if k not in arr.files:
                continue
            idx = arr[k]
            info = pl.get(name) or pl.get(k) or {}
            site = info.get("site", "B173nb_b10")
            r = place_values(S, name, site, prior, idx)
            r["ko"] = info.get("ko", name)
            r["check"] = U.CFG["places"]["list"].get(name, {}).get("check")
            js.append(r)
            n = r["patches"]
            a = r["mvs_a"]
            rows.append([r["ko"], U.PRIOR_KO[prior], fmt(n, "int"), fmt(r["area_m2"]), fmt(a["u_cm"], "v", n), fmt(r["u_prior_cm"], "v", n), fmt(a["e_cm"], "v", n),
                         fmt(r["e_prior_cm"], "v", n), fmt(a["w_med"], "rank", n), fmt(a["p_cm"], "v", n), fmt(r["p_G_cm"], "v", n), fmt(a["pW_cm"], "v", n),
                         fmt(r["gt_multi_layer_share"], "pct", n)])
    head = ["자리", "사전 정보", "패치", "넓이 m²", "u_M", "u_사전", "e_M", "e_사전", "MVS 무게 비율", "p_M", "p_G", "p_W", "참값 여러 층"]
    L.write(out, "places", f"자리마다의 값 (중앙값, cm, MVS 판 가, 고리 {S.R} m)", md_table(head, rows), js,
            "자리 패치 모두(평가 범위 밖 띠 패치가 있으면 그것도). 판 나 값과 맞춰 볼 값은 json. R1 고르게 낮은 평지붕은 확인 불가(설정 places).")


SECTIONS = dict(t1=t1, t2=t2, t61=t61, t62=t62, t63=t63, t64=t64, t65=t65, t71=t71, t72=t72, places=places)

if __name__ == "__main__":
    R = float(sys.argv[1])
    S = L.Store(R)
    out = U.DOCS / "tables" / f"R{R}"
    for sec in (sys.argv[2:] or list(SECTIONS)):
        t = U.Timer()
        SECTIONS[sec](S, out)
        U.log(sec, t.mark("s"), "s")
