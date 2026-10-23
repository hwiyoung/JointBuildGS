"""PHD-MAIN-UNCERT-v1 the answers of order 10 (questions 1-9) from the table json of one ring radius (pure functions, no data).
Grades: '그렇다 · 확인' (the 확인 column), '그렇다 · 가능·근거 불완전' (the second column), '아니다 · 확인' (the opposite rule of 10),
'섞임' (the two patch sets on opposite sides), '아직 모름' (none of these, or too few patches). scientific_verdict: null."""
import json
from pathlib import Path

POOL = {"LoD2": "세 지역 합 · LoD2", "ALS": "세 지역 합 · 항공 LiDAR"}


def jv(T, name):
    return json.loads((Path(T) / f"{name}.json").read_text())["values"]


def follow(T, data_ko, prior):
    """(rho, bins with >= 100 patches, non-increasing steps) of u vs e on the pooled patch set."""
    J = jv(T, "t61_u_vs_error")
    rk = next(r for r in J["rank"] if r["unit"] == POOL[prior] and r["data"] == data_ko)
    rho = rk["faces"]["전체"]["rho_u_e"]
    b = next(r for r in J["bins_u"] if r["unit"] == POOL[prior] and r["data"] == data_ko)["rows"]
    seq = [(x["bin"], x["p50"], x["n"]) for x in b if x["n"] >= 100]
    bad = sum(1 for a, c in zip(seq[:-1], seq[1:]) if c[1] <= a[1])
    return rho, seq, bad


def grade_follow(rho, bad):
    if rho is None:
        return "모름"
    if rho < 0.1:
        return "반대"
    if rho >= 0.5 and bad == 0:
        return "확인"
    if rho >= 0.3 or bad == 1:                 # order 10: '순위 상관 0.3 이상이거나, 커지지 않는 구간이 하나'
        return "가능"
    return "모름"


def combine(gs):
    if all(g == "확인" for g in gs):
        return "그렇다 · 확인"
    if all(g in ("확인", "가능") for g in gs):
        return "그렇다 · 가능·근거 불완전"
    if all(g == "반대" for g in gs):
        return "아니다 · 확인"
    if any(g in ("확인", "가능") for g in gs) and any(g == "반대" for g in gs):
        return "섞임"
    return "아직 모름"


def q1(T, data_ko="MVS 판 가"):
    out = {}
    for p in ("LoD2", "ALS"):
        rho, seq, bad = follow(T, data_ko, p)
        out[p] = dict(rho=rho, bins=seq, non_increasing=bad, grade=grade_follow(rho, bad))
    return combine([out[p]["grade"] for p in out]), out


def q2(T):
    rho, seq, bad = follow(T, "항공 LiDAR", "ALS")
    g = grade_follow(rho, bad)
    return combine([g]), dict(ALS=dict(rho=rho, bins=seq, non_increasing=bad, grade=g))


def q3(T, data_ko="MVS 판 가"):
    J = jv(T, "t62_roc")
    out = {}
    for p in ("LoD2", "ALS"):
        r = next(x for x in J["cells"] if x["unit"] == POOL[p] and x["data"] == data_ko and x["positives"] == "양성 전체")
        a = r["scores"]["u"]["auc"]
        g = "확인" if a is not None and a >= 0.75 else "가능" if a is not None and a >= 0.65 else "반대" if a is not None and a < 0.55 else "모름"
        out[p] = dict(auc=a, n_pos=r["scores"]["u"]["n_pos"], n_neg=r["scores"]["u"]["n_neg"], grade=g)
    return combine([out[p]["grade"] for p in out]), out


def q4(T, data_ko="MVS 판 가"):
    J = jv(T, "t63_changed")
    out = {}
    gs = []
    for r in J:
        if r["data"] != data_ko:
            continue
        out.setdefault(r["case"], {})[r["cell"]] = r["u"]["p50"], r["u"]["n"]
    for case, v in out.items():
        ref = v.get("다듬기", (None, 0))[0]
        rat = {}
        for c in ("보정 · 1~4τ", "보정 · 4τ 넘음"):
            m, n = v.get(c, (None, 0))
            if m is None or ref is None or n < 30:
                continue
            rat[c] = m / ref if ref > 0 else None
        mx = max(rat.values()) if rat else None
        g = "모름" if mx is None else "확인" if mx <= 1.5 else "가능" if mx <= 2.0 else "반대"
        v["ratio"] = rat
        v["grade"] = g
        gs.append(g)
    return combine(gs) if gs else "아직 모름", out


def q5(T):
    J = jv(T, "t64_lod2")
    out = {}
    for r in J:
        if r["group"] == "지붕면" and r["basis"] == "참값(보정 · 4τ 넘음 뺌)":
            q68 = r.get("q68_cm")
            out[r["site"]] = dict(q68_cm=q68, n=r.get("n"), inside=(q68 is not None and 15 <= q68 <= 30))
    outside = sum(1 for v in out.values() if not v["inside"])
    ans = "그렇다 · 확인" if outside == 0 else "그렇다 · 가능·근거 불완전" if outside == 1 else "아니다 · 확인"
    return ans, out


def q9(T):
    """u (지금 식) vs q (68.3 % 값) per pooled patch set (MVS 판 가): rank correlations with e, qe, f higher by more than 0.05 in two of the
    three, and the AUC of the f-defined positives higher (compared at the reported two decimals). 확인 = both conditions on both sets; 가능 =
    one condition only (on a set) without the other side winning anything; else 비슷함."""
    J = jv(T, "t61_u_vs_error")
    R = jv(T, "t62_roc")
    per = {}
    for p in ("LoD2", "ALS"):
        rk = next(r for r in J["rank"] if r["unit"] == POOL[p] and r["data"] == "MVS 판 가")["u_q_vs_three"]
        f = next(r for r in R["by_f"] if r["unit"] == POOL[p] and r["data"] == "MVS 판 가")["scores"]
        au, aq = round(f["u"]["auc"], 2), round(f["q"]["auc"], 2)
        wu = sum(1 for er in ("e", "qe", "f") if rk[f"u_{er}"] - rk[f"q_{er}"] > 0.05)
        wq = sum(1 for er in ("e", "qe", "f") if rk[f"q_{er}"] - rk[f"u_{er}"] > 0.05)
        per[p] = dict(rank={er: dict(u=rk[f"u_{er}"], q=rk[f"q_{er}"]) for er in ("e", "qe", "f")}, auc_f=dict(u=au, q=aq),
                      score_u=int(wu >= 2) + int(au > aq), score_q=int(wq >= 2) + int(aq > au), rank_wins=dict(u=wu, q=wq))
    su = [per[p]["score_u"] for p in per]
    sq = [per[p]["score_q"] for p in per]
    if all(x == 2 for x in su):
        ans = "지금 식 · 확인"
    elif all(x == 2 for x in sq):
        ans = "68.3 % 값 · 확인"
    elif sum(su) >= 1 and sum(sq) == 0:
        ans = "지금 식 · 가능·근거 불완전"
    elif sum(sq) >= 1 and sum(su) == 0:
        ans = "68.3 % 값 · 가능·근거 불완전"
    else:
        ans = "비슷함"
    return ans, per
