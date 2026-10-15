"""PHD-CH6-SUPPORT-v1 task 5 tables (jointbuildgs:dev, CPU): markdown tables from /out/t5/judge/counts.json and buildings.csv.

  python t5_tables.py

Writes /out/t5/judge/tables.md: T1 main table (per prior: items x {selection, evaluation}: area, the two relevant categories as
shares of the item area), T2 per evaluation region, T3 direct / propagated / no judgment, T4 per range (selection), T5
confidence-excluded wrong observations, T6 B173_b0 own values against fixed values, T7 concentration over buildings, T8 v6 vs
v5 checks. Shares are by area. scientific_verdict: null."""
import csv
import json

from ch6_common import ITEMS, OUT, PRIOR_KO, PRIORS, RANGES, SITE_KO

J = OUT / "t5/judge"
CATS = ("correct_keep", "wrong_keep", "correct_release", "wrong_release")
IKO = dict(ITEMS)
RIGHT = {"both_right", "image_wrong", "undecidable_passed", "unseen_missing_right", "unseen_invisible_right"}


def tot(t, item, group=None):
    d = {c: 0.0 for c in CATS + ("undetermined",)}
    n = 0
    for key, v in t.items():
        it, g = key.split("|")
        if it == item and (group is None or g == group):
            for c in d:
                d[c] += v[c][0]
            n += sum(v[c][1] for c in CATS)
    return d, n


def cell(d, item):
    a = sum(d[c] for c in CATS)
    if a <= 0:
        return "—"
    if item in RIGHT:
        return f"{a:,.0f} m² · 맞게 지킴 {100 * d['correct_keep'] / a:.1f} % · **잘못 놓음 {100 * d['wrong_release'] / a:.1f} %**"
    return f"{a:,.0f} m² · 맞게 놓음 {100 * d['correct_release'] / a:.1f} % · **잘못 지킴 {100 * d['wrong_keep'] / a:.1f} %**"


def merge(*ts):
    out = {}
    for t in ts:
        for key, v in t.items():
            o = out.setdefault(key, {c: [0.0, 0] for c in CATS + ("undetermined",)})
            for c in o:
                o[c][0] += v[c][0]; o[c][1] += v[c][1]
    return out


def main():
    R = json.loads((J / "counts.json").read_text())
    L = ["# 일 5 표 (학습 전 판정, 넓이 기준)", ""]
    ev = {p: merge(*[R["evaluation"][f"{b}/{p}"] for b in ("B0_b10", "B173nb_b10", "R1rep_b10")]) for p in PRIORS}
    # T1
    L += ["## T1 주 표: 검증 항목마다 (고르는 곳 = 일곱 범위에서 평가 범위를 뺀 곳, 평가 지역 = B0·B173 주변·R1의 평가 범위; B173만은 T6)", ""]
    for p in PRIORS:
        L += [f"**{PRIOR_KO[p]}**", "", "| 검증 항목 | 고르는 곳 | 평가 지역 |", "|---|---|---|"]
        for it, ko in ITEMS:
            a, _ = tot(R["selection"][p], it); b, _ = tot(ev[p], it)
            if sum(a[c] for c in CATS) + sum(b[c] for c in CATS) == 0:
                continue
            L.append(f"| {ko} | {cell(a, it)} | {cell(b, it)} |")
        L.append("")
    # T2 per evaluation region
    L += ["## T2 평가 지역마다", ""]
    for p in PRIORS:
        L += [f"**{PRIOR_KO[p]}**", "", "| 검증 항목 | " + " | ".join(SITE_KO[b] for b in ("B0_b10", "B173nb_b10", "R1rep_b10", "B173_b0")) + " |", "|---|---|---|---|---|"]
        for it, ko in ITEMS:
            cells = [cell(tot(R["evaluation"][f"{b}/{p}"], it)[0], it) for b in ("B0_b10", "B173nb_b10", "R1rep_b10", "B173_b0")]
            if all(c == "—" for c in cells):
                continue
            L.append(f"| {ko} | " + " | ".join(cells) + " |")
        L.append("")
    # T3 direct / propagated / none
    L += ["## T3 판정의 갈래 (고르는 곳 + 평가 지역): 직접 = 지지 패치의 표, 전파 = 결측 패치가 빌려 온 판정, 없음 = 비가시", "",
          "| 사전 정보 | 갈래 | 넓이 (m²) | 맞게 지킴 | 잘못 지킴 | 맞게 놓음 | 잘못 놓음 | 그중 미판정 (혼재·근거 부족) |", "|---|---|---|---|---|---|---|---|"]
    for p in PRIORS:
        allt = merge(R["selection"][p], ev[p])
        for g, gko in (("direct", "직접"), ("propagated", "전파"), ("none", "없음")):
            d = {c: 0.0 for c in CATS + ("undetermined",)}
            for key, v in allt.items():
                if key.split("|")[1] == g:
                    for c in d:
                        d[c] += v[c][0]
            a = sum(d[c] for c in CATS)
            if a <= 0:
                continue
            L.append(f"| {PRIOR_KO[p]} | {gko} | {a:,.0f} | " + " | ".join(f"{100 * d[c] / a:.1f} %" for c in CATS) + f" | {100 * d['undetermined'] / a:.1f} % |")
    L.append("")
    # T4 per range
    L += ["## T4 범위마다 (고르는 곳, 겹침을 빼지 않은 범위 값): 사전 정보가 맞는 곳의 잘못 놓음 몫 / 틀린 곳의 잘못 지킴 몫", "",
          "| 범위 | LoD2 맞는 곳 넓이 · 잘못 놓음 | LoD2 틀린 곳 넓이 · 잘못 지킴 | 항공 LiDAR 맞는 곳 · 잘못 놓음 | 항공 LiDAR 틀린 곳 · 잘못 지킴 |", "|---|---|---|---|---|"]
    for r in RANGES:
        cells = []
        for p in PRIORS:
            t = R["selection_per_range"][f"{r}/{p}"]
            right = {c: 0.0 for c in CATS}; wrong = {c: 0.0 for c in CATS}
            for key, v in t.items():
                it = key.split("|")[0]
                tgt = right if it in RIGHT else wrong
                for c in CATS:
                    tgt[c] += v[c][0]
            ar, aw = sum(right.values()), sum(wrong.values())
            cells.append(f"{ar:,.0f} m² · {100 * right['wrong_release'] / max(ar, 1e-9):.1f} %")
            cells.append(f"{aw:,.0f} m² · {100 * wrong['wrong_keep'] / max(aw, 1e-9):.1f} %")
        L.append(f"| {r} | " + " | ".join(cells) + " |")
    L.append("")
    # T5 mask-off supplement
    L += ["## T5 보충: 관측 신뢰도가 거른 잘못된 관측 (사전 정보 맞음, 마스크를 끈 MVS는 τ 넘게 틀림, 마스크를 켠 쪽은 결측이거나 τ 안)", "",
          "| 자리 | 사전 정보 | 넓이 (m²) | 그 가운데 판정 갈래 (직접 / 전파) | 맞게 지킴 | 잘못 놓음 |", "|---|---|---|---|---|---|"]
    for key, t in R["maskoff"].items():
        if not isinstance(t, dict):
            continue
        site, p = key.split("/") if key.count("/") == 1 else (key, "")
        d = {c: 0.0 for c in CATS}; gd = {"direct": 0.0, "propagated": 0.0, "none": 0.0}
        for k2, v in t.items():
            if k2 == "source" or "|" not in k2:
                continue
            g = k2.split("|")[1]
            for c in CATS:
                d[c] += v[c][0]
            gd[g] += sum(v[c][0] for c in CATS)
        a = sum(d.values())
        name = "고르는 곳" if site == "selection" else SITE_KO.get(site, site)
        L.append(f"| {name} | {PRIOR_KO.get(p, p)} | {a:,.1f} | {gd['direct']:,.1f} / {gd['propagated']:,.1f} | {100 * d['correct_keep'] / max(a, 1e-9):.1f} % | {100 * d['wrong_release'] / max(a, 1e-9):.1f} % |")
    L.append("")
    # T6 B173 own values
    L += ["## T6 B173만: 찾기 범위 값을 고정한 판정(본 실험)과 장면 안에서만 구한 값의 판정", ""]
    if R["b173_self"]:
        L += ["| 사전 정보 | 판정에 쓴 값 | τ 지붕 / 벽 (m) | 수직 이동 (m) | 맞게 지킴 | 잘못 지킴 | 맞게 놓음 | 잘못 놓음 |", "|---|---|---|---|---|---|---|---|"]
        for p in PRIORS:
            dfx = {c: 0.0 for c in CATS}
            for key, v in R["evaluation"][f"B173_b0/{p}"].items():
                for c in CATS:
                    dfx[c] += v[c][0]
            a = sum(dfx.values())
            s = R["b173_self"].get(p)
            if s is None:
                continue
            L.append(f"| {PRIOR_KO[p]} | 찾기 범위(R2) 값 고정 | {s['truth_tau_fixed']['roof']:.3f} / {s['truth_tau_fixed']['wall']:.3f} | 0 | " + " | ".join(f"{100 * dfx[c] / a:.1f} %" for c in CATS) + " |")
            ds = {c: s["all"][c][0] for c in CATS}; a2 = sum(ds.values())
            L.append(f"| {PRIOR_KO[p]} | 장면 안에서 구함 | {s['own_tau']['roof']:.3f} / {s['own_tau']['wall']:.3f} | {s['own_shift'][2]:+.2f} | " + " | ".join(f"{100 * ds[c] / a2:.1f} %" for c in CATS) + " |")
        L += ["", "- 참 라벨: 두 줄 모두 고정 τ(찾기 범위 값)로 정했다. 장면 안 값의 줄은 그 정합으로 옮긴 사전 정보의 정오다(옮긴 사전 정보가 실제로 학습에 들어가므로).", ""]
    # T7 concentration
    L += ["## T7 잘못된 판정이 건물에 몰린 정도 (고르는 곳)", "", "| 사전 정보 | 갈래 | 넓이 합 (m²) | 그 갈래가 있는 건물 | 가장 큰 건물의 몫 | 큰 다섯 건물의 몫 | 반을 채우는 건물 수 | 80 %를 채우는 건물 수 |", "|---|---|---|---|---|---|---|---|"]
    for p in PRIORS:
        cc = R["concentration"].get(f"selection/{p}", {})
        for c, cko in (("wrong_release", "잘못 놓음"), ("wrong_keep", "잘못 지킴")):
            x = cc.get(c)
            if not x or not x["total_m2"]:
                continue
            L.append(f"| {PRIOR_KO[p]} | {cko} | {x['total_m2']:,.0f} | {x['buildings_with_any']} / {x['buildings']} | {x['top1'][0]} {100 * x['top1'][2]:.0f} % | {100 * x['top5_share']:.0f} % | {x['n_for_50pct']} | {x['n_for_80pct']} |")
    L.append("")
    rows = list(csv.DictReader(open(J / "buildings.csv")))
    L += ["**잘못 놓음이 큰 건물 (고르는 곳, 사전 정보가 맞는 넓이 가운데 놓은 몫과 함께)**", "", "| 사전 정보 | 건물 | 범위 | 잘못 놓음 (m²) | 맞게 지킴 (m²) | 놓은 몫 |", "|---|---|---|---|---|---|"]
    for p in PRIORS:
        rr = sorted([r for r in rows if r["area_kind"] == "selection" and r["prior"] == p], key=lambda r: -float(r["wrong_release"]))[:6]
        for r in rr:
            L.append(f"| {PRIOR_KO[p]} | {r['building']} | {r['range']} | {float(r['wrong_release']):,.0f} | {float(r['correct_keep']):,.0f} | {100 * float(r['released_share_of_prior_right'] or 0):.1f} % |")
    L.append("")
    # T8 checks
    L += ["## T8 점검: v6 판정과 v5(버리는 기준 작업)의 같은 규칙 판정", "", "| 범위 · 사전 정보 | 규칙 | τ v6 = v5 | 정합 v6 = v5 | 놓음 판정이 같은 패치 몫 |", "|---|---|---|---|---|"]
    for k, v in R["checks"].items():
        L.append(f"| {k} | {v['rule']} | {'예' if v['tau_v6'] == v['tau_v5'] else '아니오'} | {'예' if v['shift_v6'] == v['shift_v5'] else '아니오'} {v['shift_v6']} | {100 * v['release_same_as_v5']:.2f} % |")
    (J / "tables.md").write_text("\n".join(L) + "\n")
    print("t5 tables written")


if __name__ == "__main__":
    main()
