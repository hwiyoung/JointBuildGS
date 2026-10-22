"""PHD-MAIN-AXES71-v2 일 4: the two-axis curves' values (jointbuildgs:dev, CPU; reads the per-point files and the cells).

  python a4_axes.py      -> AX/tables/a4_axes.json, /docs/tables/일4_두축.md|json

Axis 1 (config axes.axis1_tau): 다듬기 (0~1) and the two 보정 cells by the patch's prior misfit |gt_med| / τ: 1~1.5, 1.5~2, 2~4, 4~8, over 8;
axis 1 in m (axes.axis1_m): the 보정 cells by |gt_med|: 0~0.5, 0.5~1, 1~2, 2~4, over 4 m. Axis 2 (axes.axis2): 다듬기 (0~1) and the
patches of 보존 · 문턱 안 ('지킴'), 한계 ('놓음') and 보존 · 거름 (third line) by the patch's image-depth misfit |mvs_minus_gt_at_gt| / τ
(보존 · 거름: by the value before the filter if one exists, else one point over the cell): 1~1.5, 1.5~2, 2~4, over 4. Per bin, case (and
the three sites of a prior together) and result: 참값 기준 재현율 R(τ), 참값 기준 평균 거리, 결과 기준 정밀도 P(τ) and 결과 기준 평균 거리
(셈 마), the GT rows and the counted result points. Check: axis 1 against the distance task's 일 5 ('어긋난 크기별 재현율', DM/tables/d5_curve.json).
[이 발주에서 냄] scientific_verdict: null."""
import numpy as np

from ax_common import CASES, CFG, CID, DM, DOCS, ORDER, PRIORS, RES_KO, SITES, TAB, WORK, case_ko, jdump, jl, log, now, results_of
from ax_arrays import arrays, cat, cells, gt_block, res_block, sel

PRE = WORK / "prefilter_{site}_{prior}.npz"      # optional: per-patch misfit before the filter (일 1); absent -> one point


def edges(lst):
    return [float("inf") if e == "inf" else float(e) for e in lst]


def bins_of(site, prior, C):
    """per patch: dict line -> bin index (-1 none)."""
    cell = C["cell"].astype(np.int64)
    r1 = C["ratio1"].astype(np.float64)
    r2 = C["ratio2"].astype(np.float64)
    R = np.load(f"/out/regions_v3/regions_ext_v3_{site}_{prior}.npz")
    gm = np.abs(R["gt_med"].astype(np.float64))
    out = {}
    e1 = edges(CFG["axes"]["axis1_tau"]["edges"])
    corr = np.isin(cell, [CID["c_corr14"], CID["c_corr4p"]])
    b = np.full(len(cell), -1)
    b[cell == CID["c_refine"]] = 0
    for i in range(1, len(e1) - 1):
        b[corr & (r1 >= e1[i]) & (r1 < e1[i + 1])] = i
    out["axis1_tau"] = b
    em = edges(CFG["axes"]["axis1_m"]["edges"])
    b = np.full(len(cell), -1)
    for i in range(len(em) - 1):
        b[corr & (gm >= em[i]) & (gm < em[i + 1])] = i
    out["axis1_m"] = b
    e2 = edges(CFG["axes"]["axis2"]["edges"])
    for line, cid in (("keep", CID["c_keep_in"]), ("limit", CID["c_limit"])):
        b = np.full(len(cell), -1)
        b[cell == CID["c_refine"]] = 0
        for i in range(1, len(e2) - 1):
            b[(cell == cid) & (r2 >= e2[i]) & (r2 < e2[i + 1])] = i
        out[f"axis2_{line}"] = b
        out[f"axis2_{line}_novalue"] = int(((cell == cid) & ~np.isfinite(r2)).sum())
        out[f"axis2_{line}_below1"] = int(((cell == cid) & (r2 < 1)).sum())
    pf = PRE.with_name(PRE.name.format(site=site, prior=prior))
    b = np.full(len(cell), -1)
    b[cell == CID["c_refine"]] = 0
    if pf.exists():
        v = np.load(pf)["ratio_before"].astype(np.float64)
        for i in range(1, len(e2) - 1):
            b[(cell == CID["c_keep_mask"]) & (v >= e2[i]) & (v < e2[i + 1])] = i
        out["axis2_mask_mode"] = "거르기 전 어긋남"
    else:
        b[cell == CID["c_keep_mask"]] = 99                      # one point over the cell
        out["axis2_mask_mode"] = "한 점(거르기 전 어긋남 값 없음)"
    out["axis2_mask"] = b
    return out


LINES = (("axis1_tau", "axis1_tau"), ("axis1_m", "axis1_m"), ("axis2_keep", "axis2"), ("axis2_limit", "axis2"), ("axis2_mask", "axis2"))


def labels(ax):
    e = CFG["axes"][ax]["edges"]
    f = lambda x: "" if x == "inf" else f"{x:g}"
    return [f"{f(e[i])}~{f(e[i + 1])}" for i in range(len(e) - 1)]


def value(A_list, line, bi, binsl):
    if any(a.get("status") != "있음" for a in A_list):
        return dict(status=next(a.get("status") for a in A_list if a.get("status") != "있음"))
    g = cat([sel(a["rows"], binsl[k][line][a["rows"]["patch"]] == bi) for k, a in enumerate(A_list)])
    s = cat([sel(a["smp"], binsl[k][line][a["smp"]["patch"]] == bi) for k, a in enumerate(A_list)])
    gb, rb = gt_block(g), res_block(s, place=True)
    return dict(status="있음", n_gt=gb["n_gt"], R_tau=gb.get("R_tau"), mean=gb.get("mean"), med=gb.get("med"), n_res=rb["E"]["n"], P_tau=rb["E"].get("P_tau"),
                res_mean=rb["E"].get("mean"), excluded_share=rb["E"].get("excluded_share"))


def main():
    out, info = {}, {}
    for prior in PRIORS:
        C = {s: cells(s, prior) for s in SITES}
        B = {s: bins_of(s, prior, C[s]) for s in SITES}
        for s in SITES:
            info[f"{s}/{prior}"] = {k: v for k, v in B[s].items() if not isinstance(v, np.ndarray)}
        units = [([s], f"{s}/{prior}") for s in SITES] + [(list(SITES), f"합/{prior}")]
        for rk in ORDER:
            for res in results_of(rk, prior):
                A = {s: arrays(s, prior, res, C[s]) for s in SITES}
                for ss, u in units:
                    AL = [A[s] for s in ss]
                    BL = [B[s] for s in ss]
                    e = out.setdefault(u, {}).setdefault(rk, {}).setdefault(res, {})
                    for line, ax in LINES:
                        n_b = len(labels(ax))
                        idx = list(range(n_b)) + ([99] if line == "axis2_mask" else [])
                        e[line] = {str(i): value(AL, line, i, BL) for i in idx}
                log(prior, res)
    # the method's mean
    for u, d in out.items():
        prior = u.split("/")[1]
        r0, r1 = results_of("method", prior)
        m = {}
        for line in d["method"][r0]:
            m[line] = {}
            for i, a in d["method"][r0][line].items():
                b = d["method"][r1][line][i]
                if a.get("status") != "있음" or b.get("status") != "있음":
                    m[line][i] = dict(status=a.get("status"))
                    continue
                m[line][i] = {k: (None if a[k] is None or b[k] is None else (min(a[k], b[k]) if isinstance(a[k], int) else 0.5 * (a[k] + b[k]))) if k != "status" else "있음" for k in a}
        d["method"]["mean"] = m
    # check against the distance task's 일 5
    D5 = jl(DM / "tables/d5_curve.json")
    chk = []
    want = [("B0_b10/LoD2", "mvsfuse", "1~1.5", 31.8), ("B0_b10/LoD2", "mvsfuse", "1.5~4", 5.7), ("B173nb_b10/ALS", "method", "1~4", 86.4), ("B173nb_b10/ALS", "mvsfuse", "1~4", 48.7)]
    for u, rk, rng, w in want:
        lo, hi = [float(x) for x in rng.split("~")]
        e1 = edges(CFG["axes"]["axis1_tau"]["edges"])
        idx = [i for i in range(1, len(e1) - 1) if e1[i] >= lo and e1[i + 1] <= hi]
        site, prior = u.split("/")
        res_l = results_of(rk, prior)
        vals = []
        if any(out[u][rk][res]["axis1_tau"][str(i)].get("status") != "있음" for res in res_l for i in idx):
            chk.append(dict(case=u, result=rk, bins=rng, request=w, here=None, same=False, note="결과 없음"))
            continue
        for res in res_l:
            n = sum(out[u][rk][res]["axis1_tau"][str(i)]["n_gt"] for i in idx)
            r = sum(out[u][rk][res]["axis1_tau"][str(i)]["R_tau"] * out[u][rk][res]["axis1_tau"][str(i)]["n_gt"] for i in idx) / n
            vals.append(r)
        chk.append(dict(case=u, result=rk, bins=rng, request=w, here=round(100 * float(np.mean(vals)), 2), same=abs(round(100 * float(np.mean(vals)), 1) - w) < 0.051))
    jdump(TAB / "a4_axes.json", dict(task="PHD-MAIN-AXES71-v2", work="일 4", made=now(), rule=__doc__.split("\n\n")[1], labels={ax: labels(ax) for ax in ("axis1_tau", "axis1_m", "axis2")},
                                     info=info, data=out, checks=chk, distance_task_d5=bool(D5), scientific_verdict=None))
    write_md(out, info, chk)
    log("a4 done", chk)


def write_md(out, info, chk):
    lab = {ax: labels(ax) for ax in ("axis1_tau", "axis1_m", "axis2")}
    L = ["# 일 4 두 축 곡선의 구간 표 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 칸 = 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm) · 참값 점 수. 결과 기준(셈 마) 값은 json.",
         "- 축 1: 다듬기(0~1)와 보정 두 칸을 패치의 사전 정보 어긋남 |gt_med|/τ로 나눔. 축 2: 다듬기(0~1)와 보존 · 문턱 안('지킴'), 한계('놓음'), 보존 · 거름을 패치의 영상 깊이 어긋남 |mvs_minus_gt_at_gt|/τ로 나눔.",
         "- 본 방법 = 두 씨앗 평균. CDGS 변형 = 시점별 크기 맞추기를 생략한 변형. `*` 1만 점 미만, '표본 부족' 100점 미만.", ""]
    names = {"axis1_tau": "축 1 (τ의 배)", "axis1_m": "축 1 (m, 보정 칸만)", "axis2_keep": "축 2 · 지킴(보존 · 문턱 안)", "axis2_limit": "축 2 · 놓음(한계)", "axis2_mask": "축 2 · 보존 · 거름"}
    axof = {"axis1_tau": "axis1_tau", "axis1_m": "axis1_m", "axis2_keep": "axis2", "axis2_limit": "axis2", "axis2_mask": "axis2"}
    for u, d in out.items():
        nm = (("LoD2" if u.endswith("LoD2") else "항공 LiDAR") + " 합(세 지역)") if u.startswith("합") else case_ko(*u.split("/"))
        L += [f"## {nm}", ""]
        for line, ax in LINES:
            labs = lab[axof[line]] + (["거름 전체(한 점)"] if line == "axis2_mask" else [])
            idx = list(range(len(lab[axof[line]]))) + ([99] if line == "axis2_mask" else [])
            L += [f"**{names[line]}**", "", "| 구간 | " + " | ".join(RES_KO[k] for k in ORDER) + " |", "|---|" + "---|" * len(ORDER)]
            for i, lb in zip(idx, labs):
                cells = []
                for rk in ORDER:
                    e = d[rk]["mean"][line][str(i)] if rk == "method" else d[rk][next(iter(d[rk]))][line][str(i)]
                    if e.get("status") != "있음":
                        cells.append(e.get("status"))
                        continue
                    n = e["n_gt"]
                    if n < 100:
                        cells.append(f"표본 부족 ({n})")
                        continue
                    cells.append(f"{100 * e['R_tau']:.1f} · {e['mean']:.1f} · {n:,}" + ("*" if n < 10000 else ""))
                if all(c.startswith("표본 부족 (0)") for c in cells):
                    continue
                L.append(f"| {lb} | " + " | ".join(cells) + " |")
            L.append("")
    L += ["## 맞춰 볼 값 (새 거리 지표 일 5)", "", "| 경우 | 결과 | 구간 | 발주의 값 | 여기 | 같음 |", "|---|---|---|---:|---:|---|"]
    for c in chk:
        L.append(f"| {case_ko(*c['case'].split('/'))} | {RES_KO[c['result']]} | {c['bins']}τ | {c['request']} | {'결과 없음' if c['here'] is None else format(c['here'], '.2f')} | {'같음' if c['same'] else ('결과 없음' if c['here'] is None else '어긋남 !')} |")
    L += ["", "- 구간에 넣지 않은 패치(영상 깊이 어긋남 값 없음, 1τ 미만): " + "; ".join(
        f"{case_ko(*u.split('/'))} 지킴 {v['axis2_keep_novalue']}·{v['axis2_keep_below1']}, 놓음 {v['axis2_limit_novalue']}·{v['axis2_limit_below1']}, 거름 {v['axis2_mask_mode']}" for u, v in info.items())]
    (DOCS / "tables/일4_두축.md").write_text("\n".join(L) + "\n")
    jdump(DOCS / "tables/일4_두축.json", jl(TAB / "a4_axes.json"))


if __name__ == "__main__":
    main()
