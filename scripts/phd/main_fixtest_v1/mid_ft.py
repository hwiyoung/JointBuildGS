"""PHD-MAIN-FIXTEST-v1 8.2 중간 보고 (jointbuildgs:dev, CPU; run_step_ft.sh): the main values of the four trainings of turns 1-2 that ran
(lane 0: B0 항공 LiDAR 판 A 읽기 L and 읽기 T -- the two B173 fix-A runs of turns 1-2 were gated; lane 1: 판 B R1 LoD2 and B173 주변 항공 LiDAR),
read with order 9.2, from
  FT/tables/eval_ft.json                 tables_ft.py (d3 place values, the inflow rates, the reading of each fix)
  FT/mech/bands_<site>_<prior>_<rd>.json band_w.py (A8: band shares of the agree pixels at 30,000)
Values the order's predictions name: A1 (code 2 distance and bias), A8 (w and w~tau shares), B1 (missing R(0.2 m), B173 주변 항공 LiDAR,
with the prior-trust reference), B2 (missing R(0.2 m) and the code-13 inflow, R1 LoD2, with the judgment-only-off reference).
  python mid_ft.py
Writes FT/tables/mid_values.md and .json. scientific_verdict: null."""
import json
from pathlib import Path

PH = Path("/ph")
FTP = PH / "main_fixtest_v1/PHD-MAIN-FIXTEST-v1"
NAMES = (("lt_w", "w 안"), ("w_tau", "w~τ"), ("tau_2tau", "τ~2τ"), ("2tau_4tau", "2τ~4τ"), ("ge_4tau", "4τ 넘음"))


def f1(v, d=1):
    return "—" if v is None else f"{v:.{d}f}"


def nfmt(n):
    return "—" if n is None else f"{n:,}"


def row_line(case, mko, row, cols, refs):
    s0, s1, mean = row["s0"], row["s1"], row["mean"]
    out = [case, mko, f"{f1(s0['v'])} ({nfmt(s0['n'])})", f"{f1(s1['v'])} ({nfmt(s1['n'])})", f1(mean["v"])]
    vals = {}
    for c in cols:
        x, r = row.get(c, {}), row.get(f"read_{c}", {})
        if x.get("status") != "있음" or x.get("v") is None:
            out += ["—" if x.get("status") == "있음" else (x.get("status") or "—"), "—", r.get("grade", "—")]
        else:
            out += [f"{f1(x['v'])} ({nfmt(x.get('n'))})", f"{r['diff']:+.2f} / {r['criterion']:.2f}" if r.get("diff") is not None else "—",
                    r.get("grade", "—") + (f", {r['side']}" if r.get("side") and r.get("grade") not in ("같음", "표본 부족", "—") else "")]
        vals[c] = dict(value=x.get("v"), n=x.get("n"), status=x.get("status"), read=r)
    for k in refs:
        x = row.get(k, {})
        out.append(f"{f1(x.get('v'))} ({nfmt(x.get('n'))})" if x.get("v") is not None else (x.get("status") or "—"))
    return "| " + " | ".join(out) + " |", dict(s0=s0, s1=s1, mean=mean, fixes=vals, refs={k: row.get(k) for k in refs})


def main():
    E = json.loads((FTP / "tables/eval_ft.json").read_text())["cases"]
    J, md = {}, ["# 중간 보고 값 [이 발주에서 냄]", "",
                 "칸: 값 (표본 수). 차 / 기준 = 고친 판 − 본 방법 두 씨앗의 평균, 그리고 발주 9.2의 기준(모은 흔들림 폭, 2.8 × |씨앗 0 − 씨앗 1| ÷ √2, "
                 "몫이면 300 ÷ 표본 가운데 가장 큰 값). 읽기 = 확인(차가 기준의 두 배 넘음) / 가능·근거 불완전 / 같음, 표본 1만 점 미만은 가능·근거 불완전까지, "
                 "100점 미만은 표본 부족.", ""]
    # A1: code 2 distance and bias, B0 항공 LiDAR (both readings)
    e = E["B0_b10/ALS"]
    hdr = ["경우", "값", "본 방법 씨앗 0", "씨앗 1", "평균", "판 A 읽기 L", "차 / 기준", "읽기", "판 A 읽기 T", "차 / 기준", "읽기", "학습 전 사전 정보"]
    md += ["## A1: 두 자료가 모두 맞는 곳(코드 2)의 거리와 치우침, B0 항공 LiDAR", "", "| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    J["A1"] = {}
    for m, mko in (("dist", "거리 (cm)"), ("bias", "치우침 (cm)")):
        ln, v = row_line(e["case"], mko, e["places"]["c2"][m], ("A", "AT"), ("samepath",))
        md.append(ln)
        J["A1"][m] = v
    md.append("")
    # A3 companion for reading L (w = tau at B0 항공 LiDAR): every place, distance and R(tau)
    md += ["### 같은 두 학습의 모든 곳 거리와 R(τ) (읽기 L은 이 경우 w = τ라 A3의 값이다)", "",
           "| " + " | ".join(["곳", "값", "본 방법 씨앗 0", "씨앗 1", "평균", "판 A 읽기 L", "차 / 기준", "읽기", "판 A 읽기 T", "차 / 기준", "읽기"]) + " |", "|" + "---|" * 11]
    J["A3_B0_ALS"] = {}
    ko = {"all": "전체", "c11": "사전 정보가 틀린 곳", "c11s": "조금 틀린 곳", "c2": "두 자료가 모두 맞는 곳", "img": "영상이 틀린 곳", "c4": "결측 영역", "c5": "비가시 영역"}
    for place in ("all", "c2", "img", "c11", "c11s", "c4", "c5"):
        for m, mko in (("dist", "거리 (cm)"), ("R_tau", "R(τ) (%)")):
            ln, v = row_line(ko[place], mko, e["places"][place][m], ("A", "AT"), ())
            md.append(ln)
            J["A3_B0_ALS"][f"{place}/{m}"] = v
    md.append("")
    # A8: bands
    md += ["## A8: 판정이 일치인 화소의 렌더 깊이 구간 몫 (30,000회, B0 항공 LiDAR)", "",
           "| 읽기 | 결과 | " + " | ".join(k for _, k in NAMES) + " | 화소 수 |", "|" + "---|" * (len(NAMES) + 3)]
    J["A8"] = {}
    for rd in ("L", "T"):
        f = FTP / "mech" / f"bands_B0_b10_ALS_{rd}.json"
        if not f.exists():
            md.append(f"| {rd} | 결과 없음 | " + " | ".join("—" for _ in NAMES) + " | — |")
            continue
        d = json.loads(f.read_text())
        J["A8"][rd] = d["results"]
        for res, r in d["results"].items():
            a = r["agree"]
            md.append(f"| {rd} | {res} | " + " | ".join(f"{100 * a['shares'][k]:.2f}" for k, _ in NAMES) + f" | {a['n']:,} |")
    md.append("")
    # B1 and B2
    hdrB = ["경우", "값", "본 방법 씨앗 0", "씨앗 1", "평균", "판 B", "차 / 기준", "읽기"]
    md += ["## B1: 결측 영역의 R(0.2 m), B173 주변 항공 LiDAR (참고: 사전 정보 신뢰)", "", "| " + " | ".join(hdrB + ["사전 정보 신뢰"]) + " |", "|" + "---|" * (len(hdrB) + 1)]
    e = E["B173nb_b10/ALS"]
    ln, v = row_line(e["case"], "R(0.2 m) (%)", e["places"]["c4"]["R_0.2"], ("B",), ("trust",))
    md += [ln, ""]
    J["B1"] = v
    md += ["## B2: 결측 영역의 R(0.2 m)와 결측 영역의 과거 형상 유입률(코드 13), R1 LoD2 (참고: 판정만 끈 본 방법)", "",
           "| " + " | ".join(hdrB + ["판정만 끈 본 방법"]) + " |", "|" + "---|" * (len(hdrB) + 1)]
    e = E["R1rep_b10/LoD2"]
    J["B2"] = {}
    for m, mko in (("R_0.2", "R(0.2 m) (%)"), ("infl13", "유입률 코드 13 (%)")):
        ln, v = row_line(e["case"], mko, e["places"]["c4"][m], ("B",), ("nojudge",))
        md.append(ln)
        J["B2"][m] = v
    md.append("")
    (FTP / "tables/mid_values.md").write_text("\n".join(md))
    (FTP / "tables/mid_values.json").write_text(json.dumps(dict(task="PHD-MAIN-FIXTEST-v1", part="중간 보고", values=J, scientific_verdict=None),
                                                           indent=1, ensure_ascii=False, default=float))
    print("\n".join(md))


if __name__ == "__main__":
    main()
