"""PHD-MAIN-AXES71-v2 일 7 (10.1): the boundary distance (jointbuildgs:dev, CPU).

  python a7_boundary.py     -> AX/work/boundary_<site>_<prior>.npz, AX/tables/a7_boundary.json, /docs/tables/일7_경계거리.md|json

Per in-range patch: the distance from its centre to the nearest centre of an in-range patch of another cell (참값 없음 included; the patches
outside the range are no cell and do not count). A GT row takes its patch's distance. Bins (config boundary.edges_m): 0~0.5, 0.5~1, 1~2,
2~4, over 4 m. Per cell (and sum) x bin x result, per case and per prior over the three sites: R(τ), mean |d_g|, GT rows.
[이 발주에서 냄] scientific_verdict: null."""
import numpy as np
from scipy.spatial import cKDTree

from ax_common import CELLS, CFG, CID, DOCS, KEY_KO, ORDER, PRIORS, RES_KO, SITES, SUMS, TAB, VIRTUAL_CELLS, WORK, case_ko, jdump, log, now, results_of
from ax_arrays import arrays, cells

E = [float("inf") if x == "inf" else float(x) for x in CFG["boundary"]["edges_m"]]
LAB = [f"{E[i]:g}~{'' if not np.isfinite(E[i + 1]) else f'{E[i + 1]:g}'}" for i in range(len(E) - 1)]
KEYS = [c for c in CELLS if c not in VIRTUAL_CELLS] + list(SUMS)


def bdist(site, prior, C):
    R = np.load(f"/out/regions_v3/regions_ext_v3_{site}_{prior}.npz")
    cen = R["centre"].astype(np.float64)
    cell = C["cell"].astype(np.int64)
    bd = np.full(len(cell), np.nan)
    for c in CELLS:
        m = np.nonzero(cell == CID[c])[0]
        o = np.nonzero((cell >= 0) & (cell != CID[c]))[0]
        if len(m) and len(o):
            bd[m] = cKDTree(cen[o]).query(cen[m], workers=-1)[0]
    np.savez_compressed(WORK / f"boundary_{site}_{prior}.npz", bdist=bd)
    return bd


def ksel(cell, k):
    return np.isin(cell, [CID[c] for c in SUMS[k][1]]) if k in SUMS else cell == CID[k]


def main():
    out = {}
    for prior in PRIORS:
        C = {s: cells(s, prior) for s in SITES}
        BD = {s: bdist(s, prior, C[s]) for s in SITES}
        for rk in ORDER:
            for res in results_of(rk, prior):
                per = {}
                for s in SITES:
                    A = arrays(s, prior, res, C[s])
                    per[s] = None if A.get("status") != "있음" else dict(cell=A["rows"]["cell"], b=BD[s][A["rows"]["patch"]], hit=A["rows"]["d"] <= A["rows"]["tau"], d=A["rows"]["d"])
                for ss, u in [([s], f"{s}/{prior}") for s in SITES] + [(list(SITES), f"합/{prior}")]:
                    if any(per[s] is None for s in ss):
                        out.setdefault(u, {}).setdefault(rk, {})[res] = dict(status="결과 없음")
                        continue
                    P = {k: np.concatenate([per[s][k] for s in ss]) for k in per[ss[0]]}
                    e = {}
                    for k in KEYS:
                        m = ksel(P["cell"], k)
                        e[k] = {}
                        for i, lb in enumerate(LAB):
                            mm = m & (P["b"] >= E[i]) & (P["b"] < E[i + 1])
                            e[k][lb] = dict(rows=int(mm.sum()), R_tau=float(P["hit"][mm].mean()) if mm.any() else None, mean=float(P["d"][mm].mean() * 100) if mm.any() else None)
                    out.setdefault(u, {}).setdefault(rk, {})[res] = dict(status="있음", values=e)
                log(prior, res)
    jdump(TAB / "a7_boundary.json", dict(task="PHD-MAIN-AXES71-v2", work="일 7 경계 거리", made=now(), rule=__doc__.split("\n\n")[1], bins=LAB, data=out, scientific_verdict=None))
    jdump(DOCS / "tables/일7_경계거리.json", dict(task="PHD-MAIN-AXES71-v2", work="일 7 경계 거리", made=now(), bins=LAB, data=out, scientific_verdict=None))
    L = ["# 일 7 경계 거리 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 경계 거리 = 참값 점이 든 패치의 중심에서 다른 칸 패치(평가 범위 안)의 중심까지 가장 가까운 거리. "
         "칸 = 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm). 사전 정보마다 세 지역 합. 경우마다의 값은 json. 본 방법 = 두 씨앗 평균.", ""]
    for u, d in out.items():
        if not u.startswith("합"):
            continue
        L += [f"## {'LoD2' if u.endswith('LoD2') else '항공 LiDAR'} 합(세 지역)", "", "| 칸 | 경계 거리 (m) | 참값 점 | " + " | ".join(RES_KO[k] for k in ORDER) + " |", "|---|---|---:|" + "---|" * len(ORDER)]
        ok_r = [rk for rk in ORDER if all(d[rk][r].get("status") == "있음" for r in d[rk])]
        if not ok_r:
            continue
        for k in KEYS:
            r0 = next(iter(d[ok_r[0]]))
            for lb in LAB:
                n = d[ok_r[0]][r0]["values"][k][lb]["rows"]
                if not n:
                    continue
                cs = []
                for rk in ORDER:
                    vals = [d[rk][r] for r in d[rk]]
                    if any(v.get("status") != "있음" for v in vals):
                        cs.append("결과 없음")
                        continue
                    if n < 100:
                        cs.append("표본 부족")
                        continue
                    R = np.mean([v["values"][k][lb]["R_tau"] for v in vals])
                    M = np.mean([v["values"][k][lb]["mean"] for v in vals])
                    cs.append(f"{100 * R:.1f} · {M:.1f}")
                L.append(f"| {KEY_KO[k]} | {lb} | {n:,}{'' if n >= 10000 else '*'} | " + " | ".join(cs) + " |")
        L.append("")
    (DOCS / "tables/일7_경계거리.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
