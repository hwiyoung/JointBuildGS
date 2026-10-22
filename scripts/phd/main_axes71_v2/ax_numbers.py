"""PHD-MAIN-AXES71-v2 numbers table (order 14): /docs/두축평가_숫자표_v1.md (+ _v1_2.md ...; split at 20,000 characters).

Order: 영역 나눔 (일 2) -> 장면 전체 한눈에 (일 3) -> per cell (twelve), sum (three) and 전체: the GT table and the result table (셈 마) ->
두 축 구간 (일 4) -> 누적 분포 값 (일 5) -> 덩어리 (일 6) -> 경계 거리, 결측 (일 7) -> 결과 기준 점검 (일 8) -> 부록: 강건함, 점검 셈, 1 m, 참값 밀도.
Values one decimal; '*' under 10,000, '표본 부족' under 100, '!' differs from the record, '결과 없음'. scientific_verdict: null."""
import json

import numpy as np

import a3_tables as T3
from ax_common import CASES, CELLS, CFG, DOCS, KEY_KO, KEYS, ORDER, PRIORS, RES_KO, SUMS, TAB, case_ko, jl, now

UNITS = [f"{s}/{p}" for s, p in CASES]
SUMU = [f"합/{p}" for p in PRIORS]


def uko(u):
    return T3.uko(u)


def sec_cells():
    R = jl(DOCS / "tables/일2_영역나눔.json")
    us = UNITS + SUMU
    L = ["## 1. 영역 나눔 (일 2)", "", "- 칸 = 넓이 비율 · 영역 행 비율 · 장면 점 비율 (%). 영역 행 = 칸 지표의 참값 점(솎은 행). 장면 점 = 전체 지표의 참값 점을 대응 패치의 칸으로 넣은 것. "
         "합 = 100 % (장면 점은 '패치 없음'과 '대응 패치가 평가 범위 밖' 포함). 참값에서 뺀 칸(나무, 일시 물체)은 넣지 않음: tables/일1_정의확인.md.", "",
         "| 칸 | " + " | ".join(uko(u) for u in us) + " |", "|---|" + "---|" * len(us)]
    for k in CELLS + list(SUMS):
        cs = []
        for u in us:
            d = R["data"][u]
            c = d["cells"][k]
            sc = "—" if c.get("scene") is None else f"{100 * c['scene'] / d['scene_total']:.1f}"
            cs.append(f"{100 * c['area'] / d['area_total']:.1f} · {100 * c['rows'] / d['rows_total_in_range']:.1f} · {sc}")
        L.append(f"| {KEY_KO[k]} | " + " | ".join(cs) + " |")
    L.append("| 패치 없음 (장면 점) | " + " | ".join(f"{100 * R['data'][u]['scene_no_patch'] / R['data'][u]['scene_total']:.1f}" for u in us) + " |")
    L.append("| 대응 패치가 평가 범위 밖 (장면 점) | " + " | ".join(f"{100 * R['data'][u]['scene_owner_outside'] / R['data'][u]['scene_total']:.1f}" for u in us) + " |")
    L.append("| 평가 범위 넓이 (m²) · 영역 행 · 장면 점 | " + " | ".join(f"{R['data'][u]['area_total']:,.0f} · {R['data'][u]['rows_total_in_range']:,} · {R['data'][u]['scene_total']:,}" for u in us) + " |")
    bad = [c for c in R["checks_v4"] if not c["same"]]
    L += ["", "- v4 의도 한눈에 표와 맞춰 봄: " + "; ".join(f"{case_ko(*c['case'].split('/'))} {KEY_KO.get(c['cell'], '결측 영역')} {c['here']:,}{'' if c['same'] else ' ! (기록 ' + format(c['v4'], ',') + ')'}" for c in R["checks_v4"]) +
          ". 다듬기의 차이 = 거른 영상 오류인 코드 2 패치의 행(보존 · 거름으로 감)." if bad else "", ""]
    return L


def sec_scene(D):
    L = ["## 2. 장면 전체 한눈에 (일 3)", "", "- 장면 표면 F1 점수(τ) (%), Chamfer 거리 (cm), 참값 기준 4τ 넘는 비율 (%). 결과 기준이 든 값은 셈 마와 셈 가 두 줄. 본 방법 = 두 씨앗 평균. CDGS 변형 = 시점별 크기 맞추기를 생략한 변형.", "",
         "| 경우 | 값 | " + " | ".join(T3.head()) + " |", "|---|---|" + "---|" * len(ORDER)]
    rows = [("F1 셈 마", lambda b: b["both"]["E"]["F1_tau"], 100), ("F1 셈 가", lambda b: b["both"]["A"]["F1_tau"], 100),
            ("Chamfer 셈 마", lambda b: b["both"]["E"]["chamfer"], 1), ("Chamfer 셈 가", lambda b: b["both"]["A"]["chamfer"], 1), ("4τ 넘는 참값 점", lambda b: b["gt"]["out4"], 100)]
    R2 = jl(DOCS / "tables/일2_영역나눔.json")["data"]
    notes = []
    for u in UNITS:
        for nm, fn, sc in rows:
            cs = []
            for k in ORDER:
                b = T3.blk(D, u, k, "all")
                st = T3.status_txt(b)
                v = None if st else fn(b)
                cs.append(st or ("정의 없음" if v is None else f"{v * sc:.1f}"))
            L.append(f"| {uko(u)} | {nm} | " + " | ".join(cs) + " |")
        d = R2[u]
        notes.append(f"{uko(u)}: " + ", ".join(f"{KEY_KO[c]} {100 * d['cells'][c]['rows'] / d['rows_total_in_range']:.1f}" for c in CELLS if d["cells"][c]["rows"]))
    L += ["", "- 칸별 참값 점 비율 (영역 행, %) — " + " / ".join(notes), ""]
    return L


def sec_keys(D):
    L = ["## 3. 칸·의도별 합·전체의 참값 기준 표와 결과 기준 표 (일 3)", "", "- 열 묶음: 〔사전 정보 쪽〕 학습 전 사전 정보, GeoGS | 〔영상 쪽〕 MVS, 2DGS | 〔곳마다 정함〕 결합, CDGS 변형, 본 방법. 본 방법 = 두 씨앗 평균(씨앗은 tables/일3_<칸>.md).", ""]
    for k in KEYS + ["all"]:
        L += [f"### {KEY_KO[k]}", ""] + T3.key_tables(D, k, UNITS, seeds=False)
    return L


def sec_axes():
    J = jl(TAB / "a4_axes.json")
    lab = J["labels"]
    L = ["## 4. 두 축 곡선의 구간 표 (일 4)", "", "- 사전 정보마다 세 지역 합. 칸 = R(τ) (%) · 참값 기준 평균 거리 (cm); 참값 점은 본 방법 씨앗 0의 행 수(모든 결과 같음). 경우마다·결과 기준 값은 tables/일4_두축.json.", ""]
    names = {"axis1_tau": ("축 1 (τ의 배)", "axis1_tau"), "axis1_m": ("축 1 (m, 보정 칸)", "axis1_m"), "axis2_keep": ("축 2 지킴", "axis2"), "axis2_limit": ("축 2 놓음(한계)", "axis2"),
             "axis2_mask": ("축 2 보존 · 거름", "axis2")}
    for u in SUMU:
        d = J["data"][u]
        L += [f"**{uko(u)}**", "", "| 선 | 구간 | 참값 점 | " + " | ".join(RES_KO[k] for k in ORDER) + " |", "|---|---|---:|" + "---|" * len(ORDER)]
        for line, (nm, ax) in names.items():
            labs = lab[ax] + (["거름 전체"] if line == "axis2_mask" else [])
            idx = list(range(len(lab[ax]))) + ([99] if line == "axis2_mask" else [])
            for i, lb in zip(idx, labs):
                r0 = d["method"][next(x for x in d["method"] if x != "mean")][line][str(i)]
                n = r0.get("n_gt", 0)
                if not n:
                    continue
                cs = []
                for rk in ORDER:
                    e = d[rk]["mean"][line][str(i)] if rk == "method" else d[rk][next(iter(d[rk]))][line][str(i)]
                    cs.append(e.get("status") if e.get("status") != "있음" else ("표본 부족" if n < 100 else f"{100 * e['R_tau']:.1f} · {e['mean']:.1f}"))
                L.append(f"| {nm} | {lb} | {n:,}{'*' if n < 10000 else ''} | " + " | ".join(cs) + " |")
        L.append("")
    bad = [c for c in J["checks"] if not c["same"]]
    L += ["- 새 거리 지표 일 5와 맞춰 봄: " + "; ".join(f"{case_ko(*c['case'].split('/'))} {RES_KO[c['result']]} {c['bins']}τ {c['here']:.1f}" + ("" if c["same"] else f" ! (기록 {c['request']})") for c in J["checks"]), ""]
    return L


def from_md(path, title, keep_from=None):
    t = (DOCS / "tables" / path).read_text().split("\n")
    body = [x for x in t[1:] if not x.startswith("- 만든 때")]
    if keep_from:
        i = next((n for n, x in enumerate(body) if x.startswith(keep_from)), 0)
        body = body[i:]
    return [title, ""] + [x.replace("## ", "### ", 1) if x.startswith("## ") else x for x in body] + [""]


def pack(sections):
    files, cur = [], []
    hdr = ["# 두 축 평가 — 숫자표 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 값은 소수 첫째 자리. `*` 표본 1만 점 미만, '표본 부족' 100점 미만, `!` 기록과 다름. "
           "지표 이름: 참값 기준 재현율 R(τ), 결과 기준 정밀도 P(τ), 참값 기준 평균 거리, 결과 기준 평균 거리(셈 마 = 참값 면까지 법선 방향, 옆 거리 0.5 m 안). CDGS 변형 = 시점별 크기 맞추기를 생략한 변형.", ""]
    cur = list(hdr)
    for S in sections:
        blocks, b = [], []
        for x in S:
            b.append(x)
            if x == "":
                blocks.append(b)
                b = []
        if b:
            blocks.append(b)
        for bl in blocks:
            if len("\n".join(cur + bl)) > 19800 and len(cur) > len(hdr):
                files.append(cur)
                cur = [hdr[0] + " (이어서)", ""]
            cur += bl
    files.append(cur)
    names = []
    for i, f in enumerate(files):
        nm = "두축평가_숫자표_v1.md" if i == 0 else f"두축평가_숫자표_v1_{i + 1}.md"
        (DOCS / nm).write_text("\n".join(f) + "\n")
        names.append((nm, len("\n".join(f))))
    return names


def safe(f, *a, **kw):
    try:
        return f(*a, **kw)
    except (FileNotFoundError, TypeError, KeyError) as e:
        print("skip", getattr(f, "__name__", f), a[:1], type(e).__name__, e)
        return []


def main():
    import sys
    D = jl(TAB / "a3_metrics.json")["data"]
    upto3 = "--upto3" in sys.argv
    if upto3:
        S = [sec_cells(), sec_scene(D), sec_keys(D)]
        print(pack(S))
        return
    S = [sec_cells(), sec_scene(D), sec_keys(D), safe(sec_axes),
         safe(from_md, "일5_누적분포.md", "## 5. 누적 분포의 값 표 (일 5)"),
         safe(from_md, "일6_덩어리.md", "## 6. 덩어리 (일 6)"),
         safe(from_md, "일7_경계거리.md", "## 7. 경계 거리 (일 7)"),
         safe(from_md, "일7_결측.md", "## 7. 결측 패치의 판정 길과 정오 (일 7)", keep_from="## LoD2 합"),
         safe(from_md, "일8_결과기준점검.md", "## 8. 결과 기준 거리의 점검 (일 8)"),
         ["## 부록 A. 강건함 표 (1.2)", "", "- tables/일3_부록_강건함.md에서 전체와 의도별 합만 옮김(칸마다는 그 파일)."] + safe(strip_keys, "일3_부록_강건함.md", ["전체"] + [KEY_KO[k] for k in SUMS]),
         ["## 부록 B. 결과 기준의 점검 셈 (1.1)", "", "- tables/일3_부록_셈.md에서 전체와 의도별 합만 옮김."] + safe(strip_keys, "일3_부록_셈.md", ["전체"] + [KEY_KO[k] for k in SUMS]),
         ["## 부록 C. 1 m 넘는 비율과 1 m 상한 평균 (점검)", "", "- tables/일3_부록_1m.md에서 전체와 의도별 합만 옮김."] + safe(strip_keys, "일3_부록_1m.md", ["전체"] + [KEY_KO[k] for k in SUMS]),
         safe(from_md, "일1_참값밀도.md", "## 부록 D. 참값 밀도 (일 1)")]
    names = pack(S)
    print(names)


def strip_keys(path, keep):
    """the blocks of a table file whose heading (## or **...**) is one of `keep`."""
    t = (DOCS / "tables" / path).read_text().split("\n")
    out, on = [], False
    for x in t[1:]:
        if x.startswith("## ") and x[3:] in ("참값 기준", "결과 기준 셈 마", "결과 기준 셈 가"):
            out += ["", f"**{x[3:]}**", ""]
            continue
        if x.startswith("## ") or (x.startswith("**") and x.endswith("**")):
            name = x[3:] if x.startswith("## ") else x.strip("*").split(" — ")[0]
            on = name in keep
            if on:
                out.append(x.replace("## ", "*", 1) + "*" if x.startswith("## ") else x)
            continue
        if on:
            out.append(x)
    return out + [""]


if __name__ == "__main__":
    main()
