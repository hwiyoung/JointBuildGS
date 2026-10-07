"""PHD-MAIN-STAGE1-v1 tables (jointbuildgs:dev, CPU).

  python tables_s1.py prep35       3.5: the eight stage-0 results of B173nb_b10 with module v3 (thinned) next to the fix's numbers -> /out/tables/prep35.md, .json
  python tables_s1.py gate [site]  the gate table (order 2.2): all gate units with s_r of the eight cells (final), or the given units with the
                                   s_r of their cells (interim, provisional) -> /out/tables/gate_<final|interim>.md, .json
scientific_verdict: null."""
import json
import sys

import numpy as np

from s1_common import MF, OUT, jdump

FIXNAME = {"prop_LoD2_s0": "b1_LoD2", "prop_LoD2_s1": "b2_LoD2", "prop_ALS_s0": "b1_ALS", "prop_ALS_s1": "b2_ALS",
           "surface_LoD2": "surface_LoD2", "surface_ALS": "surface_ALS", "samepath_LoD2": "samepath_LoD2", "samepath_ALS": "samepath_ALS"}
LAB = {"prop_LoD2_s0": "LoD2 씨앗 0", "prop_LoD2_s1": "LoD2 씨앗 1", "surface_LoD2": "LoD2 그대로(표면)", "samepath_LoD2": "LoD2 그대로(같은 길)",
       "prop_ALS_s0": "항공 LiDAR 씨앗 0", "prop_ALS_s1": "항공 LiDAR 씨앗 1", "surface_ALS": "항공 LiDAR 그대로(표면)", "samepath_ALS": "항공 LiDAR 그대로(같은 길)"}


def g(d, *ks):
    for k in ks:
        if d is None:
            return None
        d = d.get(k) if isinstance(d, dict) else None
    return d


def pc(x, nd=1):
    return "—" if x is None else f"{100 * x:.{nd}f}"


def cm(x):
    return "—" if x is None else f"{100 * x:+.1f}"


ROWS = [  # (label, fix path, v3 path, format, reason)
    ("오류 유입률 · 사전 정보 오류 영역 (%)", ("spread", "prior_error", "main", "spread"), ("spread", "prior_error", "main", "spread"), pc,
     "솎기(0.1 m 칸에 한 점); 영역 v3(B173nb 참값 이동 −0.16 cm, 바뀐 넓이 LoD2 19 m²)"),
    ("판별 불가 비율 · 사전 정보 오류 영역 (%)", ("spread", "prior_error", "indeterminable_share"), ("spread", "prior_error", "indeterminable_share"), pc, "솎기"),
    ("오류 유입률 · 관측 오류 영역 (%)", ("spread", "observation_error", "main", "spread"), ("spread", "observation_error", "main", "spread"), pc, "솎기"),
    ("오류 유입률 · 관측 오류, 문턱 이내 (%) [새]", None, ("spread", "observation_error_within_threshold", "main", "spread"), pc, "전제 위배를 뺀 관측 오류(3.2; 조건 2의 영역)"),
    ("오류 유입률 · 전제 위배 영역 안 (%) [새]", None, ("spread", "premise_violation_interior", "main", "spread"), pc, "3.2"),
    ("오류 유입률 · 이중 오류 영역, 기록 (%)", ("spread", "double_error_record", "main", "spread"), ("spread", "double_error_record", "main", "spread"), pc, "솎기"),
    ("과거 형상 잔존율 · 사전 정보 오류 (%)", ("spread", "past_shape", "prior_error", "rate"), ("spread", "past_shape", "prior_error", "rate"), pc,
     "패치 단위라 솎기와 무관; 영역 v3"),
    ("과거 형상 잔존율 · 관측 오류, 출신 무관 (%)", ("spread", "past_shape", "observation_error_any_origin", "rate"), ("spread", "past_shape", "observation_error_any_origin", "rate"), pc, "영역 v3"),
    ("기하 정확도 · 완만한 지붕 편향 (cm)", ("accuracy", "gentle", "bias"), ("accuracy", "thinned", "gentle", "bias"), cm, "솎은 점(판단용)"),
    ("기하 정확도 · 완만한 지붕 NMAD (cm) [조건 3]", ("accuracy", "gentle", "nmad"), ("accuracy", "thinned", "gentle", "nmad"), cm, "솎은 점"),
    ("기하 정확도 · 가파른 지붕 편향 (cm)", ("accuracy", "steep", "bias"), ("accuracy", "thinned", "steep", "bias"), cm, "솎은 점"),
    ("기하 정확도 · 벽 편향 (cm)", ("accuracy", "wall", "bias"), ("accuracy", "thinned", "wall", "bias"), cm, "솎은 점"),
    ("완전성 · 결측 일치 0.2 m (%)", ("completeness", "missing_agreement", "all", "le_0.2"), ("completeness", "missing_agreement", "all", "le_0.2"), pc, "솎기"),
    ("완전성 · 전제 위배 둘레 0.2 m (%) [새, 조건 4]", None, ("completeness", "premise_band", "all", "le_0.2"), pc, "3.2"),
    ("상속률 · 가우시안 수준 (%)", ("unseen", "inheritance_rate_inferred"), ("unseen", "inheritance_rate_inferred"), pc, "정의 같음"),
    ("상속 · 메시 수준(가상 시점 안 2, 0.5 m) (%)", ("virtual", "below_roof_within_0_5"), ("virtual", "below_roof_within_0_5"), pc, "정의 같음"),
    ("부유 가우시안 3~20 m (개)", ("floating", "near_3_20m"), ("floating", "near_3_20m"), lambda x: "—" if x is None else f"{x:,}", "정의 같음"),
    ("요약 · Chamfer 평균 (m)", ("summary", "chamfer_mean"), ("summary", "chamfer_mean"), lambda x: "—" if x is None else f"{x:.3f}", "다시 계산(시험 계산 방식)"),
    ("요약 · F1 @0.2 m (%)", ("summary", "f1_0.2"), ("summary", "f1_0.2"), pc, "다시 계산"),
]


def prep35():
    res = {}
    for r, f in FIXNAME.items():
        unit = "LoD2" if "LoD2" in r else "ALS"
        v3 = json.loads((OUT / "metrics/B173nb_b10" / f"{r}__{unit}.json").read_text())
        fx = json.loads((MF / "metrics" / f"{f}.json").read_text())
        res[r] = dict(v3=v3, fix=fx)
    order = list(LAB)
    md = ["| 지표 | " + " | ".join(LAB[r] for r in order) + " | 바뀐 까닭 |", "|---|" + "---|" * len(order) + "---|"]
    out = {}
    for lab, fp, vp, fmt, why in ROWS:
        cells = []
        for r in order:
            a = g(res[r]["fix"], *fp) if fp else None
            b = g(res[r]["v3"], *vp)
            out.setdefault(lab, {})[r] = dict(fix=a, v3=b)
            cells.append(f"{fmt(a)} → {fmt(b)}" if fp else fmt(b))
        md.append(f"| {lab} | " + " | ".join(cells) + f" | {why} |")
    (OUT / "tables").mkdir(exist_ok=True)
    (OUT / "tables/prep35.md").write_text("\n".join(md) + "\n")
    jdump(OUT / "tables/prep35.json", dict(rows=out, scientific_verdict=None))
    print("\n".join(md))




# ------------------------------------------------------------------------------------------------ gate (order 2.2; config 'gate')
GATE_UNITS = ["B0_b10", "B173nb_b10", "R1rep_b10"]
ALL_SITES = ["B0_b10", "B173nb_b10", "B173_b0", "R1rep_b10"]
COND = {
    "1": dict(name="오류 차단: 사전 정보 오류 영역의 오류 유입률", path=("spread", "prior_error", "main", "spread"), comparator="trust", kind="lower", priors=("LoD2", "ALS")),
    "2": dict(name="오류 차단: 관측 오류 영역(문턱 이내)의 오류 유입률", path=("spread", "observation_error_within_threshold", "main", "spread"), comparator="imgonly_s0",
              kind="lower", priors=("LoD2", "ALS")),
    "3": dict(name="상호 보완: 지지 일치 완만한 지붕의 NMAD", path=("accuracy", "thinned", "gentle", "nmad"), comparator="samepath", kind="lower", priors=("LoD2",)),
    "4": dict(name="오류 차단(전제 위배): 둘레 2 m 지지 일치의 완전성 0.2 m", path=("completeness", "premise_band", "all", "le_0.2"), comparator="imgonly_s0",
              kind="not_lower", priors=("LoD2", "ALS")),
}


def metric(site, res, unit, path):
    f = OUT / "metrics" / site / f"{res}__{unit}.json"
    if not f.exists():
        return None
    return g(json.loads(f.read_text()), *path)


def gate(sites=None, tag="final"):
    """the gate table of the units of `sites` (interim: B173nb_b10 only) with s_r from the cells available."""
    from src.phd.metrics_v3 import gate as G
    sites = sites or GATE_UNITS
    samples = json.loads((OUT / "defs/gate_samples.json").read_text())["units"]
    table, rows, srs = {}, [], {}
    for c, cd in COND.items():
        pairs, cells = [], {}
        for s in ALL_SITES if tag == "final" else sites:
            for p in cd["priors"]:
                a, b = metric(s, f"prop_{p}_s0", p, cd["path"]), metric(s, f"prop_{p}_s1", p, cd["path"])
                cells[f"{s}/{p}"] = dict(s0=a, s1=b, diff=None if a is None or b is None else abs(a - b))
                pairs.append((a, b))
        s_r, dof = G.pooled_sr(pairs)
        r = G.limit(s_r)
        srs[c] = dict(s_r=s_r, dof=dof, r=r, cells=cells)
        for k, v in cells.items():
            v["flag_over_r"] = bool(v["diff"] is not None and np.isfinite(r) and v["diff"] > r)
        table[c] = {}
        for s in sites:
            for p in cd["priors"]:
                a, b = metric(s, f"prop_{p}_s0", p, cd["path"]), metric(s, f"prop_{p}_s1", p, cd["path"])
                prop = None if a is None or b is None else 0.5 * (a + b)
                comp_res = {"trust": f"trust_{p}", "imgonly_s0": "imgonly_s0", "samepath": f"samepath_{p}"}[cd["comparator"]]
                comp = metric(s, comp_res, p, cd["path"])
                n = samples.get(f"{s}/{p}", {}).get("thinned", {}).get(c)
                dec = G.decide(prop, comp, r, cd["kind"], n)
                table[c][f"{s}/{p}"] = dec
                rows.append(dict(condition=c, unit=f"{s}/{p}", proposed=prop, comparator=comp, comparator_result=comp_res,
                                 difference=None if prop is None or comp is None else comp - prop, r=r, samples=n, decision=dec))
    ok, summ = G.passes(table)
    # comparator variation (image-only seeds 0 and 1 at B173nb_b10)
    cv = {}
    for c, cd in COND.items():
        for p in cd["priors"]:
            if cd["comparator"] != "imgonly_s0":
                continue
            a, b = metric("B173nb_b10", "imgonly_s0", p, cd["path"]), metric("B173nb_b10", "imgonly_s1", p, cd["path"])
            cv[f"{c}/{p}"] = dict(s0=a, s1=b, diff=None if a is None or b is None else abs(a - b), r_proposed=srs[c]["r"])
    out = dict(tag=tag, units=sites, rows=rows, s_r=srs, decisions=table, passed=ok, summary=summ, comparator_variation=cv, scientific_verdict=None)
    jdump(OUT / "tables" / f"gate_{tag}.json", out)
    md = [f"| 조건 | 단위 | 본 방법(씨앗 0·1 평균) | 견줌 | 차이(견줌 − 본 방법) | r = 2.8 s_r | 표본 | 판정 |", "|---|---|---|---|---|---|---|---|"]
    fmt = lambda x, c: "—" if x is None else (f"{100 * x:.1f} %" if c in ("1", "2", "4") else f"{100 * x:.2f} cm")
    for rr in rows:
        c = rr["condition"]
        dif = "—" if rr["difference"] is None else "%+.2f" % (100 * rr["difference"])
        rv = "—" if not np.isfinite(rr["r"]) else "%.2f" % (100 * rr["r"])
        ns = "—" if rr["samples"] is None else "{:,}".format(rr["samples"])
        md.append("| %s | %s | %s | %s (%s) | %s | %s | %s | %s |" % (c, rr["unit"].replace("/", " · "), fmt(rr["proposed"], c), fmt(rr["comparator"], c),
                                                                  rr["comparator_result"], dif, rv, ns, rr["decision"]))
    md.append("")
    md.append(f"**통과 규칙**: {'통과' if ok else '통과 아님'} — " + "; ".join(f"조건 {c}: 충족 {v['met']}, 미충족 {v['not_met']}, 판별 불가 {v['undecidable']}, 판단 못 함 {v['not_judgeable']}"
                                                                    + (" (가를 수 없음)" if v["cannot_be_decided"] else "") for c, v in summ.items()))
    (OUT / "tables" / f"gate_{tag}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    if sys.argv[1] == "gate":
        gate(sys.argv[2:] or None, "final" if not sys.argv[2:] else "interim")
    else:
        {"prep35": prep35}[sys.argv[1]]()
