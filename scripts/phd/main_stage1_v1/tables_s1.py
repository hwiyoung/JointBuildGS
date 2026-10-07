"""PHD-MAIN-STAGE1-v1 tables (jointbuildgs:dev, CPU).

  python tables_s1.py prep35       3.5: the eight stage-0 results of B173nb_b10 with module v3 (thinned) next to the fix's numbers -> /out/tables/prep35.md, .json
  python tables_s1.py gate [site]  the gate table (order 2.2): all gate units with s_r of the eight cells (final), or the given units with the
                                   s_r of their cells (interim, provisional) -> /out/tables/gate_<final|interim>.md, .json
  python tables_s1.py gate_preview the three gate units with the s_r of their six cells (B173_b0 pending) -> /out/tables/gate_preview.md, .json
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


# ------------------------------------------------------------------------------------------------ result tables of a site (order 5)
def _num(x, f):
    return "—" if x is None else f(x)


P1 = lambda x: _num(x, lambda v: f"{100 * v:.1f}")          # share -> %
C1 = lambda x: _num(x, lambda v: f"{100 * v:+.1f}")         # m -> cm, signed
D1 = lambda x: _num(x, lambda v: f"{100 * v:.1f}")          # m -> cm
RES_ROWS = [  # (section, label, [(path, fmt), ...]) - several paths are joined by ' / '
    ("오류 차단", "유입률 · 사전 정보 오류 [조건 1]", [(("spread", "prior_error", "main", "spread"), P1)]),
    ("오류 차단", "판별 불가 · 사전 정보 오류", [(("spread", "prior_error", "indeterminable_share"), P1)]),
    ("오류 차단", "유입률 · 관측 오류 문턱 이내 [조건 2]", [(("spread", "observation_error_within_threshold", "main", "spread"), P1)]),
    ("오류 차단", "판별 불가 · 관측 오류 문턱 이내", [(("spread", "observation_error_within_threshold", "indeterminable_share"), P1)]),
    ("오류 차단", "유입률 · 관측 오류 문턱 이내, 의심 뺌", [(("spread", "observation_error_within_threshold", "main_without_suspect", "spread"), P1)]),
    ("오류 차단", "유입률 · 관측 오류 전체", [(("spread", "observation_error", "main", "spread"), P1)]),
    ("오류 차단", "유입률 · 전제 위배 안", [(("spread", "premise_violation_interior", "main", "spread"), P1)]),
    ("오류 차단", "유입률 · 이중 오류(기록)", [(("spread", "double_error_record", "main", "spread"), P1)]),
    ("오류 차단", "유입률 · 결측 사전 정보 오류(기록)", [(("spread", "missing_prior_error_record", "main", "spread"), P1)]),
    ("오류 차단", "과거 형상 · 사전 정보 오류", [(("spread", "past_shape", "prior_error", "rate"), P1)]),
    ("오류 차단", "과거 형상 · 관측 오류(출신 무관)", [(("spread", "past_shape", "observation_error_any_origin", "rate"), P1)]),
    ("오류 차단", "보정 경계 (τ / m)", [(("spread", "size_curve", "boundary_tau"), lambda x: _num(x, lambda v: f"{v:g}")),
                                    (("spread", "size_curve", "boundary_roof_m"), lambda x: _num(x, lambda v: f"{v:.2f}"))]),
    ("기하", "완만한 지붕 편향 / NMAD [조건 3 = NMAD]", [(("accuracy", "thinned", "gentle", "bias"), C1), (("accuracy", "thinned", "gentle", "nmad"), D1)]),
    ("기하", "완만한 지붕 편향, 의심 뺌", [(("accuracy", "thinned", "gentle_without_suspect", "bias"), C1)]),
    ("기하", "완만한 지붕 산포 q68.3 / q95", [(("accuracy", "thinned", "gentle", "dev_q683"), D1), (("accuracy", "thinned", "gentle", "dev_q95"), D1)]),
    ("기하", "가파른 지붕 편향 / NMAD", [(("accuracy", "thinned", "steep", "bias"), C1), (("accuracy", "thinned", "steep", "nmad"), D1)]),
    ("기하", "가파른 지붕 산포 q68.3 / q95", [(("accuracy", "thinned", "steep", "dev_q683"), D1), (("accuracy", "thinned", "steep", "dev_q95"), D1)]),
    ("기하", "띠 편향 / NMAD", [(("accuracy", "thinned", "band", "bias"), C1), (("accuracy", "thinned", "band", "nmad"), D1)]),
    ("기하", "벽 편향 / NMAD", [(("accuracy", "thinned", "wall", "bias"), C1), (("accuracy", "thinned", "wall", "nmad"), D1)]),
    ("완전성", "결측 일치 0.2 / 0.5 m", [(("completeness", "missing_agreement", "all", "le_0.2"), P1), (("completeness", "missing_agreement", "all", "le_0.5"), P1)]),
    ("완전성", "비가시 일치 0.2 / 0.5 m", [(("completeness", "invisible_agreement", "all", "le_0.2"), P1), (("completeness", "invisible_agreement", "all", "le_0.5"), P1)]),
    ("완전성", "전제 위배 둘레 0.2 m [조건 4]", [(("completeness", "premise_band", "all", "le_0.2"), P1)]),
    ("완전성", "못 본 곳 상속률 / 과거 형상 (가우시안)", [(("unseen", "inheritance_rate_inferred"), P1), (("unseen", "past_shape_invisible_inferred"), P1)]),
    ("완전성", "가상 시점 메시: 맞음 미룸 0.5 m / 틀림 미룸 0.2 m", [(("virtual", "below_roof_within_0_5"), P1), (("virtual", "above_roof_within_0_2"), P1)]),
    ("부유", "3~20 m / 그중 사전 정보 출신 / 20 m 넘게 (개)", [(("floating", "near_3_20m"), lambda x: _num(x, lambda v: f"{v:,}")),
                                                     (("floating", "near_prior"), lambda x: _num(x, lambda v: f"{v:,}")),
                                                     (("floating", "above_20m"), lambda x: _num(x, lambda v: f"{v:,}"))]),
    ("부유", "평가 영상 화소 몫 (‰)", [(("floating", "pixel_share_all"), lambda x: _num(x, lambda v: f"{1000 * v:.2f}"))]),
    ("요약", "Chamfer 평균 (m)", [(("summary", "chamfer_mean"), lambda x: _num(x, lambda v: f"{v:.3f}"))]),
    ("요약", "정밀도 / 완전성 / F1 @0.2 m", [(("summary", "precision_0.2"), P1), (("summary", "completeness_0.2"), P1), (("summary", "f1_0.2"), P1)]),
    ("요약", "M3C2 중앙값 / NMAD (cm)", [(("summary", "m3c2", "median"), C1), (("summary", "m3c2", "nmad"), D1)]),
    ("요약", "학습 시간 (분) / GPU 최대 (GB)", [(("summary", "time_memory", "wall_seconds"), lambda x: _num(x, lambda v: f"{v / 60:.0f}")),
                                       (("summary", "time_memory", "gpu_memory_used_mib", "peak_minus_idle"), lambda x: _num(x, lambda v: f"{v / 1024:.1f}"))]),
    ("요약", "화질 PSNR / SSIM / LPIPS", [(("summary", "image_quality", "psnr"), lambda x: _num(x, lambda v: f"{v:.2f}")),
                                       (("summary", "image_quality", "ssim"), lambda x: _num(x, lambda v: f"{v:.3f}")),
                                       (("summary", "image_quality", "lpips_vgg"), lambda x: _num(x, lambda v: f"{v:.3f}"))]),
]
RES_COLS = {  # unit -> [(result, label)]; a column is shown when its metrics file exists
    "LoD2": [("prop_LoD2_s0", "본 방법 0"), ("prop_LoD2_s1", "본 방법 1"), ("imgonly_s0", "영상만 0"), ("imgonly_s1", "영상만 1"),
             ("trust_LoD2", "늘 믿음(GeoGS)"), ("samepath_LoD2", "그대로(같은 길)"), ("surface_LoD2", "그대로(표면)")],
    "ALS": [("prop_ALS_s0", "본 방법 0"), ("prop_ALS_s1", "본 방법 1"), ("prop_ALS1x_s0", "1배 0"), ("imgonly_s0", "영상만 0"), ("imgonly_s1", "영상만 1"),
            ("trust_ALS", "늘 믿음"), ("samepath_ALS", "그대로(같은 길)"), ("surface_ALS", "그대로(표면)")],
}


def results(site):
    """per unit: the metrics of every result present (columns) by the rows of RES_ROWS, plus the reference biases (refbias)."""
    rb = json.loads((OUT / "tables/refbias.json").read_text())["sites"] if (OUT / "tables/refbias.json").exists() else {}
    md, js = [], {}
    for unit, cols in RES_COLS.items():
        have = [(r, lab, json.loads(f.read_text())) for r, lab in cols if (f := OUT / "metrics" / site / f"{r}__{unit}.json").exists()]
        if not have:
            continue
        ref = rb.get(f"{site}/{unit}", {})
        bm = g(ref, "building_mvs_minus_gt", "bias")
        md.append(f"\n**{site} · {unit}** (참고: 지면 MVS − 참값 {C1(ref.get('ground_mvs_minus_gt'))} cm, 같은 건물들의 완만한 지붕 MVS − 참값 {C1(bm)} cm)\n")
        md.append("| 묶음 | 지표 | " + " | ".join(lab for _, lab, _ in have) + " |")
        md.append("|---|---|" + "---|" * len(have))
        for sec, lab, paths in RES_ROWS:
            cells, vals = [], {}
            for r, _, d in have:
                parts = [fmt(g(d, *p)) for p, fmt in paths]
                vals[r] = [g(d, *p) for p, _ in paths]
                cells.append(" / ".join(parts) if any(x != "—" for x in parts) else "—")
            if all(c == "—" for c in cells):
                continue
            md.append(f"| {sec} | {lab} | " + " | ".join(cells) + " |")
            js.setdefault(unit, {})[lab] = vals
    (OUT / "tables" / f"results_{site}.md").write_text("\n".join(md) + "\n")
    jdump(OUT / "tables" / f"results_{site}.json", dict(site=site, rows=js, refbias={k: v for k, v in rb.items() if k.startswith(site)}, scientific_verdict=None))
    print("\n".join(md))


if __name__ == "__main__":
    if sys.argv[1] == "gate":
        gate(sys.argv[2:] or None, "final" if not sys.argv[2:] else "interim")
    elif sys.argv[1] == "gate_preview":          # the three gate units with the s_r of their own cells (B173_b0 pending), 2026-10-08
        gate(None, "preview")
    elif sys.argv[1] == "results":
        results(sys.argv[2])
    else:
        {"prep35": prep35}[sys.argv[1]]()
