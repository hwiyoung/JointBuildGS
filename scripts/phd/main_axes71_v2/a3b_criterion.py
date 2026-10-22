"""PHD-MAIN-AXES71-v2 일 3 (1.3): the criterion of 'differs' on the four values and the readings (jointbuildgs:dev, CPU; reads a3_metrics.json).

  python a3b_criterion.py   -> AX/tables/a3_criterion.json, /docs/tables/일3_달라졌다.md|json

The distance task's 일 4 rule (scripts/phd/main_dist71_v1/d4_counts.py) on 참값 기준 재현율 R(τ), 참값 기준 평균 거리, 결과 기준 정밀도 P(τ)
(셈 마) and 결과 기준 평균 거리 (셈 마), per key (전체, cells, sums) over the six cases:
  criterion = max(pooled spread, the case's spread, 300 / n %p for the shares)
    pooled spread = 2.8 x sqrt(mean over the cases with two seeds and n >= 10,000 of (s0 - s1)^2 / 2)   [평균 거리·결과 기준 값: 이 발주에서 새로 구함]
    case spread   = 2.8 x |s0 - s1| / sqrt 2
  comparators that train (2DGS, GeoGS, CDGS): |diff| > 2 x criterion 확인, between 가능·근거 불완전; that do not train (결합, 학습 전 사전 정보,
  MVS): > criterion 확인. n < 10,000: at most 가능·근거 불완전; n < 100: not read. n: GT side = the GT points, result side = the smallest
  counted result points of the method's seeds and the comparator. The readings stay in json and the tables folder (order 1.3).
[이 발주에서 냄] scientific_verdict: null."""
import math

import numpy as np

from ax_common import CASES, CFG, DOCS, KEY_KO, KEYS, RES_KO, TAB, case_ko, jdump, jl, log, now

METRICS = (("R_tau", "참값 기준 재현율 R(τ)", "gt", +1, True), ("mean", "참값 기준 평균 거리 (cm)", "gt", -1, False),
           ("P_tau", "결과 기준 정밀도 P(τ), 셈 마", "res", +1, True), ("mean", "결과 기준 평균 거리 (cm), 셈 마", "res", -1, False))
COMPS = ("prior", "geogs", "mvs", "twodgs", "mvsfuse", "cdgs")
TRAINS = set(CFG["results"]["trains"])


def get(block, side, key, share):
    if not str(block.get("status", "")).startswith("있음"):
        return None, 0
    if side == "gt":
        v, n = block["gt"].get(key), block["gt"].get("n_gt", 0)
    else:
        e = block["res"]["E"]
        v, n = e.get(key), e.get("n", 0)
    if v is None:
        return None, n
    return (100.0 * v if share else v), n


def main():
    D = jl(TAB / "a3_metrics.json")["data"]
    out = {}
    for key in ["all"] + KEYS:
        out[key] = {}
        for mk, ko, side, better, share in METRICS:
            mid = f"{side}:{mk}"
            seeds = {}
            for site, prior in CASES:
                u = f"{site}/{prior}"
                e = D[u]["method"]
                (a, na), (b, nb) = (get(e["values"][r][key], side, mk, share) for r in e["results"])
                seeds[u] = None if a is None or b is None else dict(s0=a, s1=b, n=min(na, nb))
            pool = [(x["s0"] - x["s1"]) ** 2 / 2 for x in seeds.values() if x and x["n"] >= 10000]
            pooled = 2.8 * math.sqrt(float(np.mean(pool))) if pool else None
            cases = {}
            for site, prior in CASES:
                u = f"{site}/{prior}"
                s = seeds[u]
                row = dict(case=case_ko(site, prior), seeds=s, comps={})
                if s is None:
                    row["status"] = "본 방법 값 없음"
                    cases[u] = row
                    continue
                mean = 0.5 * (s["s0"] + s["s1"])
                parts = dict(pooled=pooled, case=2.8 * abs(s["s0"] - s["s1"]) / math.sqrt(2), three_points=300.0 / s["n"] if share and s["n"] else None)
                crit = max(v for v in parts.values() if v is not None)
                row.update(mean=mean, criterion=crit, criterion_parts=parts)
                for c in COMPS:
                    if c not in D[u]:
                        row["comps"][c] = dict(status="결과 없음")
                        continue
                    ec = D[u][c]
                    vc, nc = get(ec["values"][ec["results"][0]][key], side, mk, share)
                    n = min(s["n"], nc)
                    if vc is None or n < 100:
                        row["comps"][c] = dict(value=vc, n=n, reading="표본 부족" if vc is not None else "값 없음")
                        continue
                    diff = mean - vc
                    good = diff * better > 0
                    mag = abs(diff)
                    grade = ("확인" if mag > 2 * crit else ("가능·근거 불완전" if mag > crit else None)) if c in TRAINS else ("확인" if mag > crit else None)
                    if grade == "확인" and n < 10000:
                        grade = "가능·근거 불완전"
                    row["comps"][c] = dict(value=vc, n=n, diff=diff, side=None if grade is None else ("본 방법이 나음" if good else "본 방법이 못함"), grade=grade)
                cases[u] = row
            out[key][mid] = dict(metric=ko, pooled=pooled, pooled_cases=len(pool), cases=cases)
        log(key, "done")
    jdump(TAB / "a3_criterion.json", dict(task="PHD-MAIN-AXES71-v2", work="일 3 (1.3)", made=now(), rule=__doc__.split("\n\n")[1], data=out, scientific_verdict=None))
    jdump(DOCS / "tables/일3_달라졌다.json", dict(task="PHD-MAIN-AXES71-v2", work="일 3 (1.3)", made=now(), rule=__doc__.split("\n\n")[1], data=out, scientific_verdict=None))
    L = ["# 일 3 '달라졌다'의 기준과 읽기 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 스크립트 `scripts/phd/main_axes71_v2/a3b_criterion.py`. 규칙은 새 거리 지표 일 4와 같다(발주 1.3).",
         "- 칸 = 비교 결과의 값 (읽기). 읽기 = '같음'(기준 안) 또는 '본 방법이 나음/못함, 확인/가능·근거 불완전'. 본 방법 = 두 씨앗 평균 (씨앗 0 · 1). `*` 표본 1만 점 미만.", ""]
    for key, mm in out.items():
        L += [f"## {KEY_KO[key]}", ""]
        for mid, d in mm.items():
            pooled = "—" if d["pooled"] is None else f"{d['pooled']:.2f}"
            L += [f"*{d['metric']}* — 모은 흔들림 폭 {pooled} ({d['pooled_cases']}경우)", "", "| 경우 | 본 방법 (씨앗 0 · 1) | 기준 | " + " | ".join(RES_KO[c] for c in COMPS) + " |",
                  "|---|---|---:|" + "---|" * len(COMPS)]
            for u, r in d["cases"].items():
                if "mean" not in r:
                    L.append(f"| {r['case']} | {r.get('status', '—')} | | " + " | ".join("—" for _ in COMPS) + " |")
                    continue
                cells = []
                for c in COMPS:
                    x = r["comps"][c]
                    if "diff" not in x:
                        cells.append(x.get("reading") or x.get("status") or "—")
                        continue
                    rd = "같음" if x["grade"] is None else f"{x['side']}, {x['grade']}"
                    cells.append(f"{x['value']:.1f} ({rd})" + ("*" if x["n"] < 10000 else ""))
                s = r["seeds"]
                L.append(f"| {r['case']} | {r['mean']:.1f} ({s['s0']:.1f} · {s['s1']:.1f}) | {r['criterion']:.2f} | " + " | ".join(cells) + " |")
            L.append("")
    (DOCS / "tables/일3_달라졌다.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
