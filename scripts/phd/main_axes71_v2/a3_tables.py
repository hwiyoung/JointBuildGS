"""PHD-MAIN-AXES71-v2 일 3 tables (jointbuildgs:dev, CPU; reads AX/tables/a3_metrics.json and /docs/tables/일2_영역나눔.json).

  python a3_tables.py   -> /docs/tables/일3_장면전체.md|json, 일3_<key>.md (one per key: GT table, result table 셈 마, seeds),
                           일3_부록_강건함.md, 일3_부록_셈.md, 일3_부록_1m.md
Values: shares in %, distances in cm, one decimal. Samples: under 100 '표본 부족', under 10,000 '*'. The method's cell = the mean of its two
seeds (the seeds in the key tables). CDGS 변형 = the variant without the per-view scale fit. [이 발주에서 냄] scientific_verdict: null."""
from ax_common import CASES, CELLS, CFG, DOCS, KEY_KO, KEYS, PRIORS, RES_KO, SUMS, TAB, case_ko, jdump, jl, now

ORD = CFG["results"]["order"]
GROUPS = CFG["results"]["groups"]
UNITS = [f"{s}/{p}" for s, p in CASES]
CN = {"A": "셈 가", "B": "셈 나", "C": "셈 다", "D": "셈 라", "E": "셈 마", "F": "셈 바"}


def head():
    cols = []
    for g, ks in GROUPS:
        for i, k in enumerate(ks):
            cols.append((f"〔{g}〕 " if i == 0 else "") + RES_KO[k])
    return cols


def uko(u):
    if u.startswith("합/"):
        return ("LoD2" if u.endswith("LoD2") else "항공 LiDAR") + " 합"
    return case_ko(*u.split("/"))


def blk(D, u, rk, key, seed=None):
    e = D[u].get(rk)
    if e is None:
        return dict(status="결과 없음")
    if rk == "method" and seed is None:
        return e["mean"][key]
    return e["values"][seed or e["results"][0]][key]


def fnum(v, n=None, nd=1, scale=1.0):
    if n is not None and n < 100:
        return "표본 부족"
    if v is None:
        return "정의 없음"
    return f"{v * scale:.{nd}f}" + ("*" if n is not None and n < 10000 else "")


def status_txt(b):
    st = b.get("status", "결과 없음")
    if str(st).startswith("있음"):
        return None
    if st == "가상 시점 메시 없음":
        return "가상 시점 메시 없음"
    return st


def gt_cell(b):
    s = status_txt(b)
    if s:
        return s
    g = b["gt"]
    n = g.get("n_gt", 0)
    if n < 100:
        return "표본 부족"
    return f"{fnum(g.get('R_tau'), None, 1, 100)} · {fnum(g.get('mean'))}" + ("*" if n < 10000 else "")


def res_cell(b, c="E"):
    s = status_txt(b)
    if s:
        return s
    e = b["res"][c]
    n = e.get("n", 0)
    if n < 100:
        return "표본 부족"
    return f"{fnum(e.get('P_tau'), None, 1, 100)} · {fnum(e.get('mean'))}" + ("*" if n < 10000 else "")


def key_tables(D, key, units=UNITS, seeds=True):
    """the two tables of one key (as in the numbers table) and, with seeds, the method's seeds."""
    H = head()
    L = [f"**{KEY_KO[key]} — 참값 기준: 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)**", "", "| 경우 | 참값 점 | " + " | ".join(H) + " |", "|---|---:|" + "---|" * len(H)]
    for u in units:
        n = next(((blk(D, u, k, key).get("gt") or {}).get("n_gt") for k in ORD if (blk(D, u, k, key).get("gt") or {}).get("n_gt") is not None),
                 blk(D, u, "method", key, D[u]["method"]["results"][0]).get("n_gt"))
        L.append(f"| {uko(u)} | {'—' if n is None else f'{n:,}'} | " + " | ".join(gt_cell(blk(D, u, k, key)) for k in ORD) + " |")
    L += ["", f"**{KEY_KO[key]} — 결과 기준(셈 마): 결과 기준 정밀도 P(τ) (%) · 결과 기준 평균 거리 (cm)**", "", "| 경우 | " + " | ".join(H) + " |", "|---|" + "---|" * len(H)]
    ex = []
    for u in units:
        L.append(f"| {uko(u)} | " + " | ".join(res_cell(blk(D, u, k, key)) for k in ORD) + " |")
        parts = []
        for k in ORD:
            b = blk(D, u, k, key)
            if status_txt(b) is None and b["res"]["n_res_all"]:
                parts.append(f"{RES_KO[k]} {100 * b['res']['E']['excluded_share']:.1f}")
        ex.append(f"{uko(u)}: " + ", ".join(parts) if parts else f"{uko(u)}: —")
    L += ["", "- 판단할 수 없는 결과 점(옆 거리 0.5 m 넘음)의 비율 (%) — " + "; ".join(ex), ""]
    if seeds:
        L += [f"*본 방법 두 씨앗 (씨앗 0 · 씨앗 1)*", "", "| 경우 | 참값 기준 | 결과 기준(셈 마) | 결과 점 셈 마 (씨앗 0 · 1) | 가장 가까운 패치까지 1 m 넘는 결과 점 (%) |", "|---|---|---|---|---|"]
        for u in units:
            e = D[u]["method"]
            a, b = (e["values"][r][key] for r in e["results"])
            if status_txt(a) or status_txt(b):
                L.append(f"| {uko(u)} | {status_txt(a) or status_txt(b)} | | | |")
                continue
            fp = " · ".join("—" if x["res"]["far_patch"] is None else f"{100 * x['res']['far_patch']:.1f}" for x in (a, b))
            L.append(f"| {uko(u)} | {gt_cell(a)} ; {gt_cell(b)} | {res_cell(a)} ; {res_cell(b)} | {a['res']['E']['n']:,} · {b['res']['E']['n']:,} | {fp} |")
        L.append("")
    return L


def scene_table(D, R2):
    H = head()
    L = ["# 일 3 장면 전체 한눈에 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 장면 표면 F1 점수(τ) = 전체의 2PR/(P+R), R = 참값 기준 재현율 R(τ), P = 결과 기준 정밀도 P(τ). "
         "Chamfer 거리 = (참값 기준 평균 거리 + 결과 기준 평균 거리) ÷ 2 (cm). 결과 기준이 든 값은 셈 마(법선 방향 거리, 옆 거리 0.5 m 안)와 셈 가(가장 가까운 참값 점까지) 두 줄. "
         "4τ 넘는 비율 = |d_g| > 4τ인 참값 점의 비율. CDGS 변형 = 시점별 크기 맞추기를 생략한 변형. 본 방법 = 두 씨앗 평균.", ""]
    rows = [("F1 셈 마", lambda b: b["both"]["E"]["F1_tau"], 100), ("F1 셈 가", lambda b: b["both"]["A"]["F1_tau"], 100),
            ("Chamfer 셈 마", lambda b: b["both"]["E"]["chamfer"], 1), ("Chamfer 셈 가", lambda b: b["both"]["A"]["chamfer"], 1),
            ("4τ 넘는 참값 점", lambda b: b["gt"]["out4"], 100)]
    js = {}
    for u in UNITS + [f"합/{p}" for p in PRIORS]:
        L += [f"**{uko(u)}**", "", "| 값 | " + " | ".join(H) + " |", "|---|" + "---|" * len(H)]
        for nm, fn, sc in rows:
            cells = []
            for k in ORD:
                b = blk(D, u, k, "all")
                if status_txt(b):
                    cells.append(status_txt(b))
                    continue
                v = fn(b)
                cells.append("정의 없음" if v is None else f"{v * sc:.1f}")
                js.setdefault(u, {}).setdefault(k, {})[nm] = v
            L.append(f"| {nm} | " + " | ".join(cells) + " |")
        d = R2["data"].get(u)
        if d:
            tot = d["rows_total_in_range"]
            sh = ", ".join(f"{KEY_KO[c]} {100 * d['cells'][c]['rows'] / tot:.1f}" for c in CELLS if d["cells"][c]["rows"])
            L += ["", f"- 칸별 참값 점 비율 (영역 행, %): {sh}"]
        L.append("")
    return L, js


def robust(D):
    H = head()
    L = ["# 일 3 부록 — 강건함 표 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", "- 칸 = 중앙값 (cm) · 평균 거리 (cm) · 4τ 넘는 비율 (%). 본 방법 = 두 씨앗 평균.", ""]
    for side, c, nm in (("gt", None, "참값 기준"), ("res", "E", "결과 기준 셈 마"), ("res", "A", "결과 기준 셈 가")):
        L += [f"## {nm}", ""]
        for key in ["all"] + KEYS:
            L += [f"**{KEY_KO[key]}**", "", "| 경우 | " + " | ".join(H) + " |", "|---|" + "---|" * len(H)]
            for u in UNITS:
                cells = []
                for k in ORD:
                    b = blk(D, u, k, key)
                    if status_txt(b):
                        cells.append(status_txt(b))
                        continue
                    e = b["gt"] if side == "gt" else b["res"][c]
                    n = e.get("n_gt") if side == "gt" else e.get("n")
                    if not n or n < 100:
                        cells.append("표본 부족")
                        continue
                    cells.append(f"{fnum(e.get('med'))} · {fnum(e.get('mean'))} · {fnum(e.get('out4'), None, 1, 100)}" + ("*" if n < 10000 else ""))
                L.append(f"| {uko(u)} | " + " | ".join(cells) + " |")
            L.append("")
    return L


def counts_tbl(D):
    L = ["# 일 3 부록 — 결과 기준의 점검 셈 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "",
         "- 셈 가: 그 칸의 결과 점 모두, d_r. 셈 나: 대응 참값 행이 없는 패치의 결과 점을 뺌. 셈 다·라: 가장 가까운 패치의 기대 간격 ≤ τ · ≤ τ/2. 셈 마·바: 옆 거리 ≤ 0.5 · 1.0 m, 법선 방향 거리.",
         "- 칸 = P(τ) (%) · 평균 (cm) · 중앙값 (cm) · 4τ 넘음 (%) · 세지 않은 점 (%) · F1(τ) (%) · Chamfer (cm). 본 방법 = 두 씨앗 평균.", ""]
    for key in ["all"] + KEYS:
        L += [f"## {KEY_KO[key]}", "", "| 경우 | 결과 | " + " | ".join(CN[c] for c in "ABCDEF") + " |", "|---|---|" + "---|" * 6]
        for u in UNITS:
            for k in ORD:
                b = blk(D, u, k, key)
                if status_txt(b):
                    L.append(f"| {uko(u)} | {RES_KO[k]} | {status_txt(b)} |" + " |" * 5)
                    continue
                cells = []
                for c in "ABCDEF":
                    e, w = b["res"][c], b["both"][c]
                    if e.get("n", 0) < 100:
                        cells.append(f"표본 부족 (뺌 {fnum(e.get('excluded_share'), None, 1, 100)})")
                        continue
                    cells.append(f"{fnum(e['P_tau'], None, 1, 100)} · {fnum(e['mean'])} · {fnum(e['med'])} · {fnum(e['out4'], None, 1, 100)} · {fnum(e['excluded_share'], None, 1, 100)} · "
                                 f"{fnum(w['F1_tau'], None, 1, 100)} · {fnum(w['chamfer'])}" + ("*" if e["n"] < 10000 else ""))
                L.append(f"| {uko(u)} | {RES_KO[k]} | " + " | ".join(cells) + " |")
        L.append("")
    return L


def onem(D):
    H = head()
    L = ["# 일 3 부록 — 1 m 넘는 비율과 1 m 상한 평균, 0.2 m 비율 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "",
         "- 참값 기준 칸 = 1 m 넘는 비율 (%) · 1 m 상한 평균 (cm) · R(0.2 m) (%); 결과 기준(셈 마) 칸 = 같은 꼴, P(0.2 m). 1 m 상한 평균은 점검용.", ""]
    for key in ["all"] + KEYS:
        for side in ("gt", "res"):
            L += [f"**{KEY_KO[key]} — {'참값 기준' if side == 'gt' else '결과 기준 셈 마'}**", "", "| 경우 | " + " | ".join(H) + " |", "|---|" + "---|" * len(H)]
            for u in UNITS:
                cells = []
                for k in ORD:
                    b = blk(D, u, k, key)
                    if status_txt(b):
                        cells.append(status_txt(b))
                        continue
                    e = b["gt"] if side == "gt" else b["res"]["E"]
                    n = e.get("n_gt") if side == "gt" else e.get("n")
                    if not n or n < 100:
                        cells.append("표본 부족")
                        continue
                    r02 = e.get("R_0.2") if side == "gt" else e.get("P_0.2")
                    cells.append(f"{fnum(e['far1'], None, 1, 100)} · {fnum(e['cap1_mean'])} · {fnum(r02, None, 1, 100)}" + ("*" if n < 10000 else ""))
                L.append(f"| {uko(u)} | " + " | ".join(cells) + " |")
            L.append("")
    return L


def main():
    D = jl(TAB / "a3_metrics.json")["data"]
    R2 = jl(DOCS / "tables/일2_영역나눔.json")
    L, js = scene_table(D, R2)
    (DOCS / "tables/일3_장면전체.md").write_text("\n".join(L) + "\n")
    jdump(DOCS / "tables/일3_장면전체.json", dict(task="PHD-MAIN-AXES71-v2", made=now(), data=js, scientific_verdict=None))
    for key in ["all"] + KEYS:
        L = [f"# 일 3 {KEY_KO[key]} (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 반올림 전 값·표본·모든 셈은 `AX/tables/a3_metrics.json` (같은 내용 tables/일3_값.json).", ""]
        L += key_tables(D, key, UNITS + [f"합/{p}" for p in PRIORS])
        nm = KEY_KO[key].replace(" · ", "_").replace(" ", "").replace("~", "-")
        (DOCS / f"tables/일3_{nm}.md").write_text("\n".join(L) + "\n")
    (DOCS / "tables/일3_부록_강건함.md").write_text("\n".join(robust(D)) + "\n")
    (DOCS / "tables/일3_부록_셈.md").write_text("\n".join(counts_tbl(D)) + "\n")
    (DOCS / "tables/일3_부록_1m.md").write_text("\n".join(onem(D)) + "\n")
    print("a3 tables done")


if __name__ == "__main__":
    main()
