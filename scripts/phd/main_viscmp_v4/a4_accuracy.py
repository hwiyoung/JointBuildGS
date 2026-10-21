"""PHD-MAIN-VISCMP-v4 일 나: 정확도 = the median of d_r (result point -> nearest GT point) over a place's result points, from the distance
task's per-point files and with its own place rule (scripts/phd/main_dist71_v1/d3_metrics.one): 전체 = all result points (q_d); a place =
the result points whose nearest prior patch lies in the place (q_place bit), B0's places reading d_r to the GT the regions use (q_d_b0gt of
the __b0gt file); 비가시 영역 = the virtual-view mesh's points (v_q_d). 셈 가 = all those points, 셈 나 = without the points of patches no GT
point belongs to (q_has_gt). The proposed method: seed 0, seed 1 and their mean (the mean of the two medians, as d3_metrics.mean_of).
Check: the precision (share d_r <= 0.2 m) from the same arrays against DM/tables/d3_metrics.json for every cell.
  python a4_accuracy.py -> /docs/tables/accuracy.json, accuracy.md   scientific_verdict: null"""
import numpy as np

import vc_common  # noqa: F401
from dm_common import CASES, DIST, METHOD_KO, METHODS, PLACE_KO, PLACES, TAB, case_ko, jl, results_of
from vc_common import DOCS, jdump, log, now

BITS = {k: 1 << i for i, k in enumerate(PLACES[1:])}


def one(site, prior, res):
    f = DIST / f"{site}_{prior}__{res}.npz"
    if not f.exists():
        return {p: dict(status="결과 없음") for p in PLACES}
    z = np.load(f)
    fb = DIST / f"{site}_{prior}__{res}__b0gt.npz"
    qpd = np.load(fb)["q_d_b0gt"].astype(np.float64) if (site == "B0_b10" and fb.exists()) else z["q_d"].astype(np.float64)
    out = {}
    for p in PLACES:
        if p == "all":
            dr, hg = z["q_d"].astype(np.float64), z["q_has_gt"].astype(bool)
        elif p == "c5":
            if "v_q_d" not in z.files:
                out[p] = dict(status="가상 시점 메시 없음"); continue
            dr, hg = z["v_q_d"].astype(np.float64), z["v_q_has_gt"].astype(bool)
        else:
            mr = (z["q_place"] & BITS[p]) > 0
            dr, hg = qpd[mr], z["q_has_gt"][mr].astype(bool)
        e = dict(status="있음")
        for cnt, sel in (("A", np.ones(len(dr), bool)), ("B", hg)):
            d = dr[sel]
            e[cnt] = dict(acc_cm=float(100 * np.median(d)) if len(d) else None, n=int(len(d)), P_0_2=float((d <= 0.2).mean()) if len(d) else None)
        out[p] = e
    return out


def main():
    D3 = jl(TAB / "d3_metrics.json")["data"]
    data, mism = {}, []
    for site, prior in CASES:
        u = f"{site}/{prior}"; data[u] = {}
        for m in METHODS:
            res = results_of(m, prior)
            vals = {r: one(site, prior, r) for r in res}
            e = dict(results=res, values=vals)
            for r in res:
                for p in PLACES:
                    mine, ref = vals[r].get(p, {}), D3[u][m]["values"][r].get(p, {})
                    for cnt, k in (("A", "P_0.2"), ("B", "Pb_0.2")):
                        a, b = (mine.get(cnt) or {}).get("P_0_2"), ref.get(k)
                        if (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-12):
                            mism.append(dict(case=u, result=r, place=p, count=cnt, mine=a, d3=b))
            if m == "method":
                mean = {}
                for p in PLACES:
                    a, b = vals[res[0]][p], vals[res[1]][p]
                    if a.get("status") != "있음" or b.get("status") != "있음":
                        mean[p] = dict(status=a.get("status")); continue
                    mean[p] = dict(status="있음", **{c: dict(acc_cm=0.5 * (a[c]["acc_cm"] + b[c]["acc_cm"]) if a[c]["acc_cm"] is not None and b[c]["acc_cm"] is not None else None,
                                                          n=min(a[c]["n"], b[c]["n"]), P_0_2=0.5 * (a[c]["P_0_2"] + b[c]["P_0_2"]) if a[c]["P_0_2"] is not None else None)
                                                   for c in ("A", "B")})
                e["mean"] = mean
            data[u][m] = e
        log(u, "done")
    checks = {}
    for (u, m, c, want) in (("B173nb_b10/ALS", "mvsfuse", "A", 48.6), ("B173nb_b10/ALS", "method", "A", 71.4), ("B0_b10/ALS", "mvsfuse", "A", 31.8),
                            ("B0_b10/ALS", "prior", "A", 31.9), ("B173nb_b10/ALS", "mvsfuse", "B", 48.6), ("B173nb_b10/ALS", "method", "B", 72.9)):
        e = data[u][m]["mean"]["all"] if m == "method" else data[u][m]["values"][data[u][m]["results"][0]]["all"]
        got = 100 * e[c]["P_0_2"]
        checks[f"{u} {METHOD_KO[m]} 셈 {'가' if c == 'A' else '나'}"] = dict(want=want, got=round(got, 2), ok=abs(round(got, 1) - want) < 0.051)
    out = dict(task="PHD-MAIN-VISCMP-v4", work="일 나", made=now(), rule=__doc__.split("\n\n")[0], places=PLACE_KO, data=data, precision_check=dict(mismatches=mism, n_mismatch=len(mism)),
               request_checks=checks, scientific_verdict=None)
    jdump(DOCS / "tables/accuracy.json", out)
    order = ["prior", "twodgs", "geogs", "mvsfuse", "cdgs", "method"]
    name = {"prior": "학습 전 사전 정보", "twodgs": "2DGS", "geogs": "GeoGS", "mvsfuse": "결합", "cdgs": "CDGS", "method": "본 방법(평균)"}

    def cell(u, m, p, c):
        e = data[u][m]["mean"][p] if m == "method" else data[u][m]["values"][data[u][m]["results"][0]][p]
        if e.get("status") != "있음":
            return "결과 없음" if e.get("status") == "결과 없음" else e.get("status")
        x = e[c]
        if x["acc_cm"] is None or x["n"] < 100:
            return "표본 부족"
        return f"{x['acc_cm']:.1f}" + ("*" if x["n"] < 10000 else "")
    L = ["# 정확도 (cm) — 일 나 [이 발주에서 냄]", "", f"- 정확도 = 결과 점에서 가장 가까운 참값 점까지 거리(d_r)의 중앙값. 만든 때 {out['made']}. 출처: `PH/main_dist71_v1/PHD-MAIN-DIST71-v1/dist/*.npz`(q_d, q_place, q_has_gt; B0의 곳은 `__b0gt`의 q_d_b0gt; 비가시 영역은 v_q_d).",
         "- 셈 가 = 그 곳의 결과 점 모두, 셈 나 = 참값 점이 하나도 대응하지 않은 패치의 결과 점을 뺀 것. `*` = 표본 1만 점 미만, '표본 부족' = 100점 미만. 본 방법은 두 씨앗 중앙값의 평균.",
         f"- 대조: 같은 배열에서 낸 정밀도(0.2 m)가 새 거리 지표 `d3_metrics.json`과 다른 칸 {len(mism)}개.", ""]
    for p in PLACES:
        L += [f"## {PLACE_KO[p]} (셈 가)", "", "| 경우 | " + " | ".join(name[m] for m in order) + " |", "|---|" + "---:|" * len(order)]
        for site, prior in CASES:
            u = f"{site}/{prior}"
            L.append(f"| {case_ko(site, prior)} | " + " | ".join(cell(u, m, p, "A") for m in order) + " |")
        L.append("")
    L += ["## 전체: 셈 가와 셈 나", "", "| 경우 | " + " | ".join(f"{name[m]} 가 / 나" for m in order) + " |", "|---|" + "---:|" * len(order)]
    for site, prior in CASES:
        u = f"{site}/{prior}"
        L.append(f"| {case_ko(site, prior)} | " + " | ".join(f"{cell(u, m, 'all', 'A')} / {cell(u, m, 'all', 'B')}" for m in order) + " |")
    L += ["", "## 맞춰 볼 값 (정밀도 0.2 m, 전체)", "", "| 칸 | 발주 | 이 셈 | 같음 |", "|---|---:|---:|---|"]
    for k, v in checks.items():
        L.append(f"| {k} | {v['want']:.1f} % | {v['got']:.2f} % | {'예' if v['ok'] else '아니오'} |")
    (DOCS / "tables/accuracy.md").write_text("\n".join(L) + "\n")
    log("mismatches", len(mism), checks)


if __name__ == "__main__":
    main()
