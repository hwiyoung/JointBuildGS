"""PHD-MAIN-FIXTEST-v1 9.1-9.2 / 13 (jointbuildgs:dev, CPU; run_step_ft.sh): the place tables of the new distance metric and the inflow rates,
with the reading rule of order 9.2, from
  FT/tables/d3_ft.json   (dm_ft.py d3: d3_metrics.one of the dist71 task on this task's results, the references and the method's seeds)
  metrics json           spread.prior_error.main.spread (과거 형상 유입률, code 11) and spread.missing_prior_error_record.main.spread
                         (결측 영역의 과거 형상 유입률, code 13) of metrics_s2 / metrics_s1: this task FT/metrics, the method S1/metrics,
                         the judgment-only-off method S3/metrics, the prior before training / image only S1/metrics
  criteria               the dist71 task's pooled noise bands (SD/tables/d4_counts.json: F1 0.2 m, F1 tau, 거리 for the places but 전체), the
                         past-shape inflow pooled band 1.64 %p (S2/prep/ruler.json gate 1, the fill task 9.1); a metric without one takes the other
                         two terms: the case band 2.8 |s0 - s1| / sqrt 2 and, for a share, 300 / samples (%p); criterion = the largest
Reading (order 9.2, one seed): |fix - method mean| > 2 x criterion -> 확인; > criterion -> 가능·근거 불완전; else 같음; samples < 10,000 ->
at most 가능·근거 불완전, < 100 -> 표본 부족 (not read); direction 나음 / 같음 / 못함 (거리 and inflow lower, R and F1 higher are better).
A + B is not read (values and its two differences).
  python tables_ft.py
Writes FT/tables/eval_ft.json, FT/tables/place_<place>.md, FT/tables/numbers_<n>.md (the user's number table, split at 20,000 chars).
scientific_verdict: null."""
import json
import math
from pathlib import Path

import numpy as np

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
S1 = Path("/out")
S2 = PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1"
S3 = PH / "main_stage3_v1/PHD-MAIN-STAGE3-v1"
SD = PH / "main_dist71_v1/PHD-MAIN-DIST71-v1"
CFG = json.loads(Path("/repo/configs/phd/main_fixtest_v1/fixtest_v1.json").read_text())
SITES = ("B0_b10", "B173nb_b10", "R1rep_b10")
PRIORS = ("LoD2", "ALS")
CASES = [(s, p) for s in SITES for p in PRIORS]
SITE_KO = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
PRIOR_KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
PLACES = ("all", "c11", "c11s", "c2", "img", "c4", "c5")
PLACE_KO = {"all": "전체", "c11": "사전 정보가 틀린 곳", "c11s": "조금 틀린 곳", "c2": "두 자료가 모두 맞는 곳", "img": "영상이 틀린 곳",
            "c4": "결측 영역", "c5": "비가시 영역"}
FIX_COLS = (("A", "판 A (읽기 L)"), ("AT", "판 A (읽기 T)"), ("B", "판 B"), ("AB", "함께 켠 판"))
SHARE = {"R_0.2", "R_tau", "R_0.5", "F1_0.2", "F1_tau", "F1_0.5", "P_0.2", "P_tau", "infl11", "infl13"}
LOWER = {"dist", "infl11", "infl13"}
UNIT = {"dist": "cm", "bias": "cm", "spread": "cm"}


def jl(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def pooled_bands():
    d = jl(SD / "tables/d4_counts.json")["data"]
    out = {}
    for place, ms in d.items():
        for m, v in ms.items():
            if v.get("pooled") is not None:
                out[(place, m)] = float(v["pooled"])
    r = jl(S2 / "prep/ruler.json")
    g1 = r["gate"]["1"]["r"] if r and "gate" in r else 0.016356
    out[("c11", "infl11")] = 100.0 * float(g1)
    return out


def run_status(site, res):
    if not res.startswith("fix"):
        return "있음"
    run = next((r for r in CFG["runs"] if r["site"] == site and r["result"] == res), None)
    if run is not None and not run["train"]:
        return "읽기 L과 같음" if "갈음" in run["why"] else ("관문" if "관문" in run["why"] else "학습 안 함")
    f = FTP / "runs" / site / res / "receipt.json"
    if not f.exists():
        return "결과 없음"
    st = json.loads(f.read_text()).get("status")
    return "있음" if st == "PASS" else f"결과 없음({st})"


def metrics_file(site, res, prior):
    for base in (FTP / "metrics", S3 / "metrics", S1 / "metrics", S2 / "metrics"):
        f = base / site / f"{res}__{prior}.json"
        if f.exists():
            return f
    return None


def inflow(site, res, prior):
    f = metrics_file(site, res, prior)
    if f is None:
        return {}
    sp = json.loads(f.read_text()).get("spread", {})
    a, b = sp.get("prior_error", {}).get("main", {}), sp.get("missing_prior_error_record", {}).get("main", {})
    return dict(infl11=None if a.get("spread") is None else 100 * a["spread"], n_infl11=a.get("points"),
                infl13=None if b.get("spread") is None else 100 * b["spread"], n_infl13=b.get("points"), source=str(f).replace(str(PH), "PH").replace("/out", "S1"))


def val(block, m):
    if not block or not str(block.get("status", "")).startswith("있음"):
        return None, None
    v = block.get(m)
    if v is None:
        return None, None
    n = block.get("n_gt") if m.startswith(("R_", "dist", "bias", "spread")) else (block.get("n_res") if m.startswith("P_") else min(block.get("n_gt") or 0, block.get("n_res") or 0))
    return (100 * v if m in SHARE and not m.startswith("infl") else v), n


def read(fixv, v0, v1, n, m, place, pooled):
    if fixv is None or v0 is None or v1 is None:
        return dict(grade="—")
    mean = 0.5 * (v0 + v1)
    terms = {"case": 2.8 * abs(v0 - v1) / math.sqrt(2)}
    if (place, m) in pooled:
        terms["pooled"] = pooled[(place, m)]
    if m in SHARE and n:
        terms["300/n"] = 300.0 / n
    crit = max(terms.values())
    diff = fixv - mean
    if n is not None and n < 100:
        return dict(grade="표본 부족", diff=diff, criterion=crit, terms=terms, n=n)
    if abs(diff) > 2 * crit:
        g = "확인"
    elif abs(diff) > crit:
        g = "가능·근거 불완전"
    else:
        g = "같음"
    if g == "확인" and n is not None and n < 10000:
        g = "가능·근거 불완전"
    if g == "같음":
        side = "같음"
    elif m == "bias":
        side = "아래로" if diff < 0 else "위로"
    else:
        side = "나음" if ((diff < 0) == (m in LOWER)) else "못함"
    return dict(grade=g, side=side, diff=diff, criterion=crit, terms=terms, n=n)


def main():
    d3 = jl(FTP / "tables/d3_ft.json")["data"]
    pooled = pooled_bands()
    E = {}
    for site, prior in CASES:
        key = f"{site}/{prior}"
        vals = d3.get(key, {})
        res = {"s0": f"prop_{prior}_s0", "s1": f"prop_{prior}_s1", **{c: f"fix{c}_{prior}_s0" for c, _ in FIX_COLS},
               "nojudge": f"nojudge_{prior}_s0", "imgonly": "imgonly_s0", "samepath": f"samepath_{prior}", "trust": "trust_ALS" if prior == "ALS" else None,
               "ablband": {("B173nb_b10", "ALS"): "abl_band_ALS_s0", ("R1rep_b10", "LoD2"): "abl_band_LoD2_s0"}.get((site, prior))}
        e = dict(case=f"{SITE_KO[site]} {PRIOR_KO[prior]}", results=res, status={k: (run_status(site, r) if r else None) for k, r in res.items()}, places={})
        infl = {k: (inflow(site, r, prior) if r else {}) for k, r in res.items()}
        e["inflow_sources"] = {k: v.get("source") for k, v in infl.items()}
        for place in PLACES:
            pe = {}
            metrics = ["dist", "R_tau", "R_0.2", "bias", "spread", "F1_0.2", "F1_tau", "P_0.2"]
            for m in metrics:
                row = {}
                for k, r in res.items():
                    if r is None:
                        continue
                    b = (vals.get(r) or {}).get("places", {}).get(place)
                    v, n = val(b, m)
                    row[k] = dict(v=v, n=n, status=e["status"][k])
                v0, v1 = row["s0"]["v"], row["s1"]["v"]
                row["mean"] = dict(v=None if v0 is None or v1 is None else 0.5 * (v0 + v1), n=row["s0"]["n"])
                for c, _ in FIX_COLS:
                    if c == "AB":
                        continue
                    fx = row.get(c, {})
                    row[f"read_{c}"] = read(fx.get("v"), v0, v1, fx.get("n") or row["s0"]["n"], m, place, pooled) if fx.get("status") == "있음" else dict(grade=fx.get("status") or "—")
                pe[m] = row
            if place in ("c11", "c4"):
                im = "infl11" if place == "c11" else "infl13"
                row = {k: dict(v=infl[k].get(im), n=infl[k].get(f"n_{im}"), status=e["status"][k]) for k in res if res[k]}
                v0, v1 = row["s0"]["v"], row["s1"]["v"]
                row["mean"] = dict(v=None if v0 is None or v1 is None else 0.5 * (v0 + v1), n=row["s0"]["n"])
                for c, _ in FIX_COLS:
                    if c == "AB":
                        continue
                    fx = row.get(c, {})
                    row[f"read_{c}"] = read(fx.get("v"), v0, v1, fx.get("n") or row["s0"]["n"], im, place, pooled) if fx.get("status") == "있음" else dict(grade=fx.get("status") or "—")
                pe[im] = row
            e["places"][place] = pe
        E[key] = e
    (FTP / "tables").mkdir(parents=True, exist_ok=True)
    (FTP / "tables/eval_ft.json").write_text(json.dumps(dict(task="PHD-MAIN-FIXTEST-v1", rule=__doc__.split("\n\n")[0], pooled={f"{a}|{b}": v for (a, b), v in pooled.items()},
                                                             cases=E, scientific_verdict=None), indent=1, ensure_ascii=False, default=float))
    write_numbers(E)
    print("tables_ft done")


def cell(x, digits=1):
    v, n, st = x.get("v"), x.get("n"), x.get("status")
    if st and st != "있음":
        return st
    if v is None:
        return "결과 없음" if st != "있음" else "—"
    if n is not None and n < 100:
        return "표본 부족"
    s = f"{v:.{digits}f}"
    return s + ("*" if n is not None and n < 10000 else "")


def rcell(r):
    g = r.get("grade", "—")
    if g in ("확인", "가능·근거 불완전"):
        return f"{g}, {r.get('side')} ({r['diff']:+.1f})"
    return g


def write_numbers(E):
    out_md = []
    for place in PLACES:
        mets = [("dist", "거리 (cm)"), ("R_tau", "R(τ) (%)")]
        if place == "c4":
            mets += [("R_0.2", "R(0.2 m) (%)"), ("infl13", "결측 영역의 과거 형상 유입률 (%, 코드 13)")]
        if place == "c11":
            mets += [("infl11", "과거 형상 유입률 (%, 코드 11)")]
        if place == "c2":
            mets += [("bias", "치우침 (cm)")]
        for m, mko in mets:
            hdr = ["경우", "본 방법 씨앗 0", "씨앗 1", "평균"] + [lab for _, lab in FIX_COLS] + ["기준"] + [f"{lab}의 읽기" for c, lab in FIX_COLS if c != "AB"] + \
                  ["판정만 끈 본 방법", "영상만", "학습 전 사전 정보"]
            lines = [f"### {PLACE_KO[place]} — {mko}", "", "| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
            for key, e in E.items():
                row = e["places"][place].get(m)
                if row is None:
                    continue
                crit = None
                for c in ("A", "AT", "B"):
                    rr = row.get(f"read_{c}", {})
                    if rr.get("criterion") is not None:
                        crit = rr["criterion"]
                        break
                cells = [e["case"], cell(row["s0"]), cell(row["s1"]), cell(row["mean"])] + [cell(row.get(c, {"status": "—"})) for c, _ in FIX_COLS] + \
                        ["—" if crit is None else f"{crit:.1f}"] + [rcell(row.get(f"read_{c}", {})) for c, _ in FIX_COLS if c != "AB"] + \
                        [cell(row.get(k, {"status": "—"})) for k in ("nojudge", "imgonly", "samepath")]
                lines.append("| " + " | ".join(cells) + " |")
            out_md.append("\n".join(lines) + "\n")
    text = "\n".join(out_md)
    parts, cur = [], ""
    for blk in out_md:
        if len(cur) + len(blk) > 19000 and cur:
            parts.append(cur)
            cur = ""
        cur += blk + "\n"
    parts.append(cur)
    for i, p_ in enumerate(parts, 1):
        (FTP / "tables" / f"numbers_part{i}.md").write_text(p_)
    (FTP / "tables/numbers_all.md").write_text(text)


if __name__ == "__main__":
    main()
