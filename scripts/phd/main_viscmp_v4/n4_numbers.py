"""PHD-MAIN-VISCMP-v4 숫자표 (request 8): 정확도_정밀도_숫자표_v4.md from tables/accuracy.json (일 나) and tables/precision_split.json (일 다).
  일 나  one table per place: rows = six cases, columns = six results, accuracy (cm, 셈 가); then 전체 셈 가 and 셈 나 side by side
  일 다  one table per case and place (전체, 두 자료가 모두 맞는 곳): rows = six results, columns = per slope bin the share of the result
         points, 정밀도, '1 m 안', '1 m 밖' ('가까움' = 정밀도), and the excluded share of all points
Values one decimal; '*' = sample < 10,000; '표본 부족' = < 100; '결과 없음'. Split into two files when over 20,000 characters.
  python n4_numbers.py   scientific_verdict: null"""
import vc_common  # noqa: F401
from vc_common import DOCS, jl, log, now

CASES = [("B0_b10", "LoD2"), ("B0_b10", "ALS"), ("B173nb_b10", "LoD2"), ("B173nb_b10", "ALS"), ("R1rep_b10", "LoD2"), ("R1rep_b10", "ALS")]
SK = {"B0_b10": "B0", "B173nb_b10": "B173 주변", "R1rep_b10": "R1"}
PK = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
RES = [("prior", "학습 전 사전 정보"), ("twodgs", "2DGS"), ("geogs", "GeoGS"), ("mvsfuse", "결합"), ("cdgs", "CDGS"), ("method", "본 방법(평균)")]


def acc_cell(v, k):
    """v = accuracy.json data[case][method]; the mean entry for the method, else the one result."""
    if v is None:
        return "결과 없음"
    e = v.get("mean") if v.get("mean") else (v["values"][v["results"][0]] if v.get("values") else None)
    if e is None:
        return "결과 없음"
    x = e.get(k) if isinstance(e, dict) else None
    return x


def fmt_acc(x, part="A"):
    if not x or x.get("status") not in (None, "있음"):
        return "결과 없음"
    a = x.get(part)
    if not a or a.get("n") is None:
        return "결과 없음"
    if a["n"] < 100:
        return "표본 부족"
    return f"{a['acc_cm']:.1f}" + ("*" if a["n"] < 10000 else "")


def main():
    A = jl(DOCS / "tables/accuracy.json"); S = jl(DOCS / "tables/precision_split.json")
    places = A["places"]
    L = ["# 정확도·정밀도 숫자표 v4 [이 발주에서 냄]", "",
         f"- 만든 때 {now()}. 출처: `tables/accuracy.json`(일 나), `tables/precision_split.json`(일 다). 반올림 전 값은 json에 있다.",
         "- 정확도 = 결과 점에서 가장 가까운 참값 점까지 거리(d_r)의 중앙값(cm). 정밀도 = d_r ≤ 0.2 m인 결과 점의 몫(%).",
         "- `*` = 표본 1만 점 미만, '표본 부족' = 100점 미만, '결과 없음' = 결과 파일 없음. 본 방법(평균) = 두 씨앗 값의 평균.", "", "## 일 나 — 정확도 (cm, 셈 가)", ""]
    D = A["data"]
    for pk, pname in places.items():
        L += [f"### {pname}", "", "| 경우 | " + " | ".join(n for _, n in RES) + " |", "|---|" + "---:|" * len(RES)]
        for s, p in CASES:
            u = f"{s}/{p}"
            L.append(f"| {SK[s]} · {PK[p]} | " + " | ".join(fmt_acc(acc_cell(D[u].get(k), pk)) for k, _ in RES) + " |")
        L.append("")
    L += ["### 전체 — 셈 가와 셈 나", "", "셈 나 = 참값 점이 하나도 대응하지 않은 패치의 결과 점을 뺀 것.", "",
          "| 경우 | " + " | ".join(f"{n} 가 | {n} 나" for _, n in RES) + " |", "|---|" + "---:|" * (2 * len(RES))]
    for s, p in CASES:
        u = f"{s}/{p}"
        L.append(f"| {SK[s]} · {PK[p]} | " + " | ".join(f"{fmt_acc(acc_cell(D[u].get(k), 'all'), 'A')} | {fmt_acc(acc_cell(D[u].get(k), 'all'), 'B')}" for k, _ in RES) + " |")
    L += ["", "## 일 다 — 정밀도를 기울기로 나눔 (%)", "",
          "- 기울기 = 결과 점이 놓인 삼각형 법선과 연직축의 각: 완만한 면 0–30°, 가파른 면 30–60°, 벽 같은 면 60–90°. 몫 = 그 곳의 결과 점 가운데 그 구간의 몫.",
          "- 정밀도 = '가까움'(d_r ≤ 0.2 m)의 몫. '1 m 안' = 0.2 < d_r ≤ 1.0 m, '1 m 밖' = d_r > 1.0 m. 세 관계의 몫의 합 = 100.",
          "- 뺀 칸 = 참값에서 뺀 0.5 m 칸에 든 결과 점의 몫(모든 점). 결과 표본은 참값 칸 안에서만 뽑히므로 모든 칸에서 0.0이다.", ""]
    SN = ["완만한 면", "가파른 면", "벽 같은 면"]
    SH = {"완만한 면": "완만", "가파른 면": "가파름", "벽 같은 면": "벽"}
    head = "| 결과 | " + " | ".join(f"{SH[b]} 몫 | {SH[b]} 정밀도 | {SH[b]} 1 m 안 | {SH[b]} 1 m 밖" for b in SN) + " | 모두 정밀도 | 뺀 칸 |"
    for s, p in CASES:
        u = f"{s}/{p}"
        for pl, plko in (("all", "전체"), ("c2", "두 자료가 모두 맞는 곳")):
            L += [f"### {SK[s]} · {PK[p]} · {plko}", "", head, "|---|" + "---:|" * (4 * len(SN) + 2)]
            for k, nm in RES:
                d = S["data"][u].get(k)
                if d is None:
                    L.append(f"| {nm} | " + " | ".join(["결과 없음"] + [""] * (4 * len(SN) + 1)) + " |"); continue
                cells = []
                for b in SN:
                    x = d[pl][b]; n = x.get("n") or 0
                    if n < 100:
                        cells += ["표본 부족", "", "", ""]; continue
                    st = "*" if n < 10000 else ""
                    cells += [f"{100 * x['share']:.1f}", f"{100 * x['P_0_2']:.1f}{st}", f"{100 * x['rel'][1]:.1f}", f"{100 * x['rel'][2]:.1f}"]
                a = d[pl]["모두"]; na = a.get("n") or 0
                cells += ([f"{100 * a['P_0_2']:.1f}" + ("*" if na < 10000 else ""), f"{100 * a['excluded']:.1f}"] if na >= 100 else ["표본 부족", ""])
                L.append(f"| {nm} | " + " | ".join(cells) + " |")
            L.append("")
    text = "\n".join(L) + "\n"
    out = DOCS / "정확도_정밀도_숫자표_v4.md"
    if len(text) <= 20000:
        out.write_text(text); log("one file", len(text))
    else:
        i = text.index("## 일 다")
        p1 = text[:i] + "\n(일 다는 `정확도_정밀도_숫자표_v4_2.md`)\n"
        p2 = "# 정확도·정밀도 숫자표 v4 — 둘째 파일 [이 발주에서 냄]\n\n" + "\n".join(L[2:6]) + "\n\n" + text[i:]
        out.write_text(p1); (DOCS / "정확도_정밀도_숫자표_v4_2.md").write_text(p2); log("two files", len(p1), len(p2))


if __name__ == "__main__":
    main()
