"""PHD-MAIN-AXES71-v2 일 5: cumulative distributions of |d_g| / τ (and of the result-side distance 셈 마 / τ) per cell (jointbuildgs:dev, CPU).

  python a5_cdf.py      -> AX/tables/a5_cdf.json (curves on a grid 0~8 τ, values), /docs/tables/일5_누적분포.md|json

Cells: config cdf.cells. Per case and per prior (three sites together), per result (the method: two seeds and the mean curve). Values per
cell x result: mean (no cap), 1 m cap mean (check), median, 90 %, 95 % and the share over 4τ, in cm and in τ multiples (d / τ of each point).
The invisible cell reads the virtual-view mesh where it exists. [이 발주에서 냄] scientific_verdict: null."""
import numpy as np

from ax_common import CFG, DOCS, KEY_KO, ORDER, PRIORS, RES_KO, SITES, SUMS, TAB, VIRTUAL_CELLS, case_ko, jdump, log, now, results_of
from ax_arrays import arrays, cat, cell_sel, cells, res_vals, sel

GRID = np.linspace(0, CFG["cdf"]["x_max_tau"], CFG["cdf"]["n_grid"])


def stats(d, t):
    if not len(d):
        return dict(n=0)
    r = d / t
    q = lambda a, p: float(np.percentile(a, p))
    return dict(n=int(len(d)), mean_cm=100 * float(d.mean()), cap1_mean_cm=100 * float(np.minimum(d, 1).mean()), med_cm=100 * q(d, 50), p90_cm=100 * q(d, 90),
                p95_cm=100 * q(d, 95), out4=float((r > 4).mean()), mean_tau=float(r.mean()), med_tau=q(r, 50), p90_tau=q(r, 90), p95_tau=q(r, 95),
                cdf=[float(x) for x in np.searchsorted(np.sort(r), GRID, side="right") / len(r)])


def one(A_list, key):
    if any(a.get("status") != "있음" for a in A_list):
        return dict(status=next(a.get("status") for a in A_list if a.get("status") != "있음"))
    if key in VIRTUAL_CELLS:
        if any("vrows" not in a for a in A_list):
            return dict(status="가상 시점 메시 없음")
        g = cat([sel(a["vrows"], cell_sel(a["vrows"]["cell"], key, SUMS)) for a in A_list])
        s = cat([sel(a["vsmp"], cell_sel(a["vsmp"]["cell"], key, SUMS)) for a in A_list])
    else:
        g = cat([sel(a["rows"], cell_sel(a["rows"]["cell"], key, SUMS)) for a in A_list])
        s = cat([sel(a["smp"], cell_sel(a["smp"]["cell"], key, SUMS)) for a in A_list])
    d, ok = res_vals(s, "E", True)
    return dict(status="있음", gt=stats(g["d"], g["tau"]), res=stats(d[ok], s["tau"][ok]))


def main():
    keys = CFG["cdf"]["cells"]
    out = {}
    for prior in PRIORS:
        C = {s: cells(s, prior) for s in SITES}
        units = [([s], f"{s}/{prior}") for s in SITES] + [(list(SITES), f"합/{prior}")]
        for rk in ORDER:
            for res in results_of(rk, prior):
                A = {s: arrays(s, prior, res, C[s]) for s in SITES}
                for ss, u in units:
                    out.setdefault(u, {}).setdefault(rk, {})[res] = {k: one([A[s] for s in ss], k) for k in keys}
                log(prior, res)
    jdump(TAB / "a5_cdf.json", dict(task="PHD-MAIN-AXES71-v2", work="일 5", made=now(), grid_tau=GRID.tolist(), data=out, scientific_verdict=None))
    L = ["# 일 5 누적 분포의 값 표 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 참값 기준 |d_g|. 칸 = 평균 · 1 m 상한 평균 · 중앙값 · 90 % · 95 % (cm) | "
         "평균 · 중앙값 · 90 % · 95 % (τ의 배) | 4τ 넘음 (%). 본 방법 = 씨앗 0의 값과 씨앗 1의 값의 평균. 결과 기준(셈 마)의 같은 값과 곡선은 json.", ""]
    for u, d in out.items():
        if not u.startswith("합"):
            continue
        L += [f"## {'LoD2' if u.endswith('LoD2') else '항공 LiDAR'} 합(세 지역)", ""]
        for k in keys:
            L += [f"**{KEY_KO[k]}**", "", "| 결과 | n | cm: 평균 · 상한 · 중앙 · 90 · 95 | τ배: 평균 · 중앙 · 90 · 95 | 4τ 넘음 |", "|---|---:|---|---|---:|"]
            for rk in ORDER:
                vals = [d[rk][r][k] for r in d[rk]]
                if any(v.get("status") != "있음" for v in vals):
                    L.append(f"| {RES_KO[rk]} | — | {vals[0].get('status')} | | |")
                    continue
                gs = [v["gt"] for v in vals]
                if gs[0]["n"] < 100:
                    L.append(f"| {RES_KO[rk]} | {gs[0]['n']} | 표본 부족 | | |")
                    continue
                m = {x: float(np.mean([g[x] for g in gs])) for x in gs[0] if x not in ("n", "cdf")}
                L.append(f"| {RES_KO[rk]} | {gs[0]['n']:,} | {m['mean_cm']:.1f} · {m['cap1_mean_cm']:.1f} · {m['med_cm']:.1f} · {m['p90_cm']:.1f} · {m['p95_cm']:.1f} | "
                         f"{m['mean_tau']:.2f} · {m['med_tau']:.2f} · {m['p90_tau']:.2f} · {m['p95_tau']:.2f} | {100 * m['out4']:.1f} |")
            L.append("")
    (DOCS / "tables/일5_누적분포.md").write_text("\n".join(L) + "\n")
    jdump(DOCS / "tables/일5_누적분포.json", dict(task="PHD-MAIN-AXES71-v2", work="일 5", made=now(), grid_tau=GRID.tolist(), data=out, scientific_verdict=None))


if __name__ == "__main__":
    main()
