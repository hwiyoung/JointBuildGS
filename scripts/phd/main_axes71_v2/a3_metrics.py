"""PHD-MAIN-AXES71-v2 일 3: the four values and the appendix values per cell x case x result (jointbuildgs:dev, CPU; reads the per-point files).

  python a3_metrics.py      -> AX/tables/a3_metrics.json (unrounded values, samples, every count)

Keys: 전체 (all), the twelve cells and the three sums of 5.1. Per case and per prior (the three sites' points together). GT side (1.1):
참값 기준 재현율 R(τ), 참값 기준 평균 거리 (mean |d_g|, no cap) and the appendix values (1.2); the region rows for a cell, the scene GT for 전체.
Result side: the result points whose nearest patch is in the cell (전체: every result point), 셈 가-바 (config metrics.counts; 셈 마 = the
table's), each with 결과 기준 정밀도 P(τ), 결과 기준 평균 거리 and the appendix values, the share of points not counted (판단할 수 없는 결과 점
for 셈 마·바, out of range for 셈 나·다·라) and the share of result points more than 1 m from their nearest patch centre. F1 and Chamfer per
count. The invisible cells are read on the virtual-view mesh where it exists ('가상 시점 메시 없음' otherwise). The method: both seeds and
their mean (each value the mean of the two). [이 발주에서 냄] scientific_verdict: null."""
import time

import numpy as np

from ax_common import CASES, CFG, KEYS, ORDER, PRIORS, SITES, SUMS, TAB, VIRTUAL_CELLS, jdump, log, now, results_of
from ax_arrays import arrays, cat, cell_sel, cells, combine, gt_block, res_block, sel

RESKEYS = ORDER + ["mvs_b"]


def blocks_of(A_list, key):
    """the value block of one key over one or several (site) arrays of one result."""
    if any(a.get("status") != "있음" for a in A_list):
        st = next(a.get("status") for a in A_list if a.get("status") != "있음")
        return dict(status=st)
    allk = key == "all"
    if key in VIRTUAL_CELLS:
        if any("vrows" not in a for a in A_list):
            n = sum(int(cell_sel(a["rows"]["cell"], key, SUMS).sum()) for a in A_list)
            return dict(status="가상 시점 메시 없음", n_gt=n)
        g = cat([sel(a["vrows"], cell_sel(a["vrows"]["cell"], key, SUMS)) for a in A_list])
        s = cat([sel(a["vsmp"], cell_sel(a["vsmp"]["cell"], key, SUMS)) for a in A_list])
        st = "있음 (가상 시점 메시)"
    elif allk:
        g = cat([a["scene"] for a in A_list])
        s = cat([a["smp"] for a in A_list])
        st = "있음"
    else:
        g = cat([sel(a["rows"], cell_sel(a["rows"]["cell"], key, SUMS)) for a in A_list])
        s = cat([sel(a["smp"], cell_sel(a["smp"]["cell"], key, SUMS)) for a in A_list])
        st = "있음"
    gb = gt_block(g, with05=allk)
    rb = res_block(s, place=not allk, with05=allk)
    return dict(status=st, gt=gb, res=rb, both=combine(gb, rb))


def mean_block(a, b):
    """the mean of two seeds' blocks (numbers averaged; counts: the smaller)."""
    if not str(a.get("status", "")).startswith("있음") or not str(b.get("status", "")).startswith("있음"):
        return dict(status=a.get("status") if not str(a.get("status", "")).startswith("있음") else b.get("status"), n_gt=a.get("n_gt"))

    def m(x, y):
        if isinstance(x, dict):
            return {k: m(x.get(k), y.get(k)) for k in x}
        if x is None or y is None:
            return None
        if isinstance(x, bool) or isinstance(x, str):
            return x
        if isinstance(x, int):
            return min(x, y)
        return 0.5 * (x + y)
    return m(a, b)


def main():
    T0 = time.time()
    data = {}
    units = [(s, p, f"{s}/{p}") for s, p in CASES] + [(None, p, f"합/{p}") for p in PRIORS]
    for prior in PRIORS:
        Cs = {s: cells(s, prior) for s in SITES}
        for rk in RESKEYS:
            for res in (results_of(rk, prior) if rk != "mvs_b" else ["mvs_b"]):
                A = {s: arrays(s, prior, res, Cs[s]) for s in SITES}
                for site, p, u in units:
                    if p != prior:
                        continue
                    L = [A[site]] if site else [A[s] for s in SITES]
                    e = data.setdefault(u, {}).setdefault(rk, {"results": results_of(rk, prior) if rk != "mvs_b" else ["mvs_b"], "values": {}})
                    e["values"][res] = {k: blocks_of(L, k) for k in ["all"] + KEYS}
                del A
                log(prior, rk, res, f"{time.time() - T0:.0f}s")
        for u in [x[2] for x in units if x[1] == prior]:
            e = data[u]["method"]
            r0, r1 = e["results"]
            e["mean"] = {k: mean_block(e["values"][r0][k], e["values"][r1][k]) for k in ["all"] + KEYS}
    jdump(TAB / "a3_metrics.json", dict(task="PHD-MAIN-AXES71-v2", work="일 3", made=now(), rule=__doc__.split("\n\n")[1], counts=CFG["metrics"]["counts"],
                                        data=data, seconds=round(time.time() - T0, 1), scientific_verdict=None))
    log("a3 done", f"{time.time() - T0:.0f}s")


if __name__ == "__main__":
    main()
