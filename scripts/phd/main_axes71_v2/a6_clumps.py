"""PHD-MAIN-AXES71-v2 일 6 (9.2): clumps of the cells and their values (jointbuildgs:dev, CPU).

  python a6_clumps.py      -> AX/work/clumps_<site>_<prior>.npz (clump id and area per patch), AX/tables/a6_clumps.json,
                              /docs/tables/일6_덩어리.md|json

Per case and cell: the in-range patches of the cell are linked when their centres are within config clumps.link_m (0.36 m; the median
centre spacing of 일 1 is 0.25 m, inside 0.18~0.36, so the link stays 0.36 m), connected components = clumps (scipy cKDTree.query_pairs +
connected_components). Per cell x case (and per prior over the three sites): clump count, clump area median / 90 % / max, share of the
cell area in the largest clump, shares of the cell area in clumps under 1, 2.5 and 10 m2, share of the cell area in boundary patches
(a patch of another in-range cell within the link distance). Per clump of 2.5 m2 or more (json also 1 m2 or more) and result: R(τ),
mean |d_g| and the GT rows. Clump hit rate: share of the clumps of 2.5 m2 (10 m2) or more with more than 50 % of their GT rows within τ.
Size bins: GT rows by the area of their clump (under 1, 1~2.5, 2.5~10, over 10 m2): R(τ), mean, rows. [이 발주에서 냄] scientific_verdict: null."""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from ax_common import CELLS, CFG, CID, DOCS, KEY_KO, ORDER, PRIORS, RES_KO, SITES, TAB, VIRTUAL_CELLS, WORK, case_ko, jdump, log, now, results_of
from ax_arrays import arrays, cells

K = CFG["clumps"]
LINK = float(K["link_m"])
SB = [float("inf") if x == "inf" else float(x) for x in K["size_bins_m2"]]


def clumps(site, prior, C):
    R = np.load(f"/out/regions_v3/regions_ext_v3_{site}_{prior}.npz")
    cen = R["centre"].astype(np.float64)
    area = C["area"].astype(np.float64)
    cell = C["cell"].astype(np.int64)
    cid = np.full(len(cell), -1, np.int64)
    carea = np.zeros(len(cell))
    boundary = np.zeros(len(cell), bool)
    ev = cell >= 0
    tree_all = cKDTree(cen[ev])
    idx_all = np.nonzero(ev)[0]
    base = 0
    for c in CELLS:
        m = np.nonzero(cell == CID[c])[0]
        if not len(m):
            continue
        t = cKDTree(cen[m])
        pr = t.query_pairs(LINK, output_type="ndarray")
        G = coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(m), len(m))) if len(pr) else coo_matrix((len(m), len(m)))
        n, lab = connected_components(G, directed=False)
        cid[m] = lab + base
        a = np.bincount(lab, weights=area[m], minlength=n)
        carea[m] = a[lab]
        base += n
        # boundary: another in-range cell's patch within the link
        nb = tree_all.query_ball_point(cen[m], LINK, workers=-1)
        boundary[m] = [bool(np.any(cell[idx_all[j]] != CID[c])) for j in nb]
    np.savez_compressed(WORK / f"clumps_{site}_{prior}.npz", clump=cid, clump_area=carea, boundary=boundary)
    return cid, carea, boundary


def stats_of(cell, cid, carea, area, boundary, c):
    m = cell == CID[c]
    if not m.any():
        return dict(patches=0)
    ids, first = np.unique(cid[m], return_index=True)
    ca = carea[m][first]
    tot = float(area[m].sum())
    q = lambda p: float(np.percentile(ca, p))
    o = dict(patches=int(m.sum()), area=tot, clumps=int(len(ids)), clump_area_p50=q(50), clump_area_p90=q(90), clump_area_max=float(ca.max()),
             largest_share=float(ca.max() / tot), boundary_share=float(area[m & boundary].sum() / tot))
    for th in K["size_thresholds_m2"]:
        o[f"under_{th:g}"] = float(area[m & (carea < th)].sum() / tot)
    for th in (K["object_min_m2"], 1.0, K["object_big_m2"]):
        o[f"clumps_ge_{th:g}"] = int((ca >= th).sum())
    return o


def main():
    out = dict(stats={}, values={}, hit={}, sizebin={})
    for prior in PRIORS:
        C = {s: cells(s, prior) for s in SITES}
        CL = {s: clumps(s, prior, C[s]) for s in SITES}
        for s in SITES:
            cid, carea, bd = CL[s]
            out["stats"][f"{s}/{prior}"] = {c: stats_of(C[s]["cell"].astype(np.int64), cid, carea, C[s]["area"].astype(np.float64), bd, c) for c in CELLS}
        # pooled over the three sites (clump ids made distinct)
        cellP = np.concatenate([C[s]["cell"].astype(np.int64) for s in SITES])
        off, cidP = 0, []
        for s in SITES:
            cidP.append(np.where(CL[s][0] >= 0, CL[s][0] + off, -1))
            off += int(CL[s][0].max()) + 1
        cidP = np.concatenate(cidP)
        careaP = np.concatenate([CL[s][1] for s in SITES])
        bdP = np.concatenate([CL[s][2] for s in SITES])
        areaP = np.concatenate([C[s]["area"].astype(np.float64) for s in SITES])
        out["stats"][f"합/{prior}"] = {c: stats_of(cellP, cidP, careaP, areaP, bdP, c) for c in CELLS}
        log(prior, "clumps")
        for rk in ORDER:
            for res in results_of(rk, prior):
                per = {}
                for k_s, s in enumerate(SITES):
                    A = arrays(s, prior, res, C[s])
                    if A.get("status") != "있음":
                        per[s] = None
                        continue
                    rows = A["rows"]
                    pa = rows["patch"]
                    off_s = sum(int(CL[x][0].max()) + 1 for x in SITES[:k_s])
                    per[s] = dict(cell=rows["cell"], clump=np.where(CL[s][0][pa] >= 0, CL[s][0][pa] + off_s, -1), carea=CL[s][1][pa], hit=rows["d"] <= rows["tau"], d=rows["d"])
                for ss, u in [([s], f"{s}/{prior}") for s in SITES] + [(list(SITES), f"합/{prior}")]:
                    if any(per[s] is None for s in ss):
                        out["values"].setdefault(u, {}).setdefault(rk, {})[res] = dict(status="결과 없음")
                        continue
                    P = {k: np.concatenate([per[s][k] for s in ss]) for k in ("cell", "clump", "carea", "hit", "d")}
                    vals, hit, sb = {}, {}, {}
                    for c in CELLS:
                        if c in VIRTUAL_CELLS:
                            continue
                        m = P["cell"] == CID[c]
                        if not m.any():
                            continue
                        cl, ca, h, d = P["clump"][m], P["carea"][m], P["hit"][m], P["d"][m]
                        ids, inv = np.unique(cl, return_inverse=True)
                        n = np.bincount(inv)
                        r = np.bincount(inv, weights=h.astype(float)) / n
                        mean = np.bincount(inv, weights=d) / n * 100
                        are = np.zeros(len(ids))
                        are[inv] = ca
                        big = are >= 1.0
                        vals[c] = dict(clump=ids[big].tolist(), area=are[big].tolist(), rows=n[big].tolist(), R_tau=r[big].tolist(), mean=mean[big].tolist())
                        hit[c] = {f"ge_{th:g}": dict(clumps=int((are >= th).sum()), hit=int(((are >= th) & (r > K["hit_share"])).sum()),
                                                     rate=float(((are >= th) & (r > K["hit_share"])).sum() / max((are >= th).sum(), 1)) if (are >= th).any() else None)
                                  for th in (K["object_min_m2"], K["object_big_m2"])}
                        sb[c] = {}
                        for i in range(len(SB) - 1):
                            mm = (ca >= SB[i]) & (ca < SB[i + 1])
                            sb[c][f"{SB[i]:g}~{'' if not np.isfinite(SB[i + 1]) else f'{SB[i + 1]:g}'}"] = dict(rows=int(mm.sum()), R_tau=float(h[mm].mean()) if mm.any() else None,
                                                                                                                mean=float(d[mm].mean() * 100) if mm.any() else None)
                    out["values"].setdefault(u, {}).setdefault(rk, {})[res] = dict(status="있음", clumps=vals)
                    out["hit"].setdefault(u, {}).setdefault(rk, {})[res] = hit
                    out["sizebin"].setdefault(u, {}).setdefault(rk, {})[res] = sb
                log(prior, res)
    jdump(TAB / "a6_clumps.json", dict(task="PHD-MAIN-AXES71-v2", work="일 6", made=now(), rule=__doc__.split("\n\n")[1], link_m=LINK, data=out, scientific_verdict=None))
    jdump(DOCS / "tables/일6_덩어리.json", dict(task="PHD-MAIN-AXES71-v2", work="일 6", made=now(), link_m=LINK, stats=out["stats"], hit=out["hit"], sizebin=out["sizebin"],
                                             note="덩어리마다의 값은 AX/tables/a6_clumps.json values", scientific_verdict=None))
    write_md(out)


def mean_seeds(d, rk, f):
    if rk not in d:
        return None
    vals = [f(d[rk][r]) for r in d[rk]]
    if any(v is None for v in vals):
        return None
    return float(np.mean(vals))


def write_md(out):
    L = ["# 일 6 덩어리 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 같은 칸의 패치를 중심 거리 {LINK} m 안으로 이음(일 1의 이웃 패치 간격 중앙값 0.25 m).", ""]
    L += ["## 칸마다 덩어리 통계", "", "| 경우 | 칸 | 덩어리 | 넓이 50 % · 90 % · 최대 (m²) | 가장 큰 덩어리 (%) | 1 · 2.5 · 10 m² 미만 덩어리의 넓이 (%) | 경계 패치 넓이 (%) | 2.5 m² 이상 덩어리 |",
          "|---|---|---:|---|---:|---|---:|---:|"]
    for u, st in out["stats"].items():
        nm = (("LoD2" if u.endswith("LoD2") else "항공 LiDAR") + " 합") if u.startswith("합") else case_ko(*u.split("/"))
        for c in CELLS:
            o = st[c]
            if not o.get("patches"):
                continue
            L.append(f"| {nm} | {KEY_KO[c]} | {o['clumps']:,} | {o['clump_area_p50']:.2f} · {o['clump_area_p90']:.2f} · {o['clump_area_max']:.1f} | {100 * o['largest_share']:.1f} | "
                     f"{100 * o['under_1']:.1f} · {100 * o['under_2.5']:.1f} · {100 * o['under_10']:.1f} | {100 * o['boundary_share']:.1f} | {o['clumps_ge_2.5']:,} |")
    L += ["", "## 덩어리 단위 달성률 (참값 점의 50 %를 넘게 τ 안인 덩어리의 비율, %) — 사전 정보마다 세 지역 합", "",
          "| 사전 정보 | 칸 | 크기 | " + " | ".join(RES_KO[k] for k in ORDER) + " |", "|---|---|---|" + "---|" * len(ORDER)]
    for u, d in out["hit"].items():
        if not u.startswith("합") or "method" not in d:
            continue
        pk = "LoD2" if u.endswith("LoD2") else "항공 LiDAR"
        cs = [c for c in CELLS if c in d["method"][next(iter(d["method"]))]]
        for c in cs:
            for th in ("ge_2.5", "ge_10"):
                n = d["method"][next(iter(d["method"]))][c][th]["clumps"]
                if not n:
                    continue
                cells_ = []
                for rk in ORDER:
                    v = mean_seeds(d, rk, lambda e: (e.get(c) or {}).get(th, {}).get("rate"))
                    cells_.append("—" if v is None else f"{100 * v:.1f}")
                L.append(f"| {pk} | {KEY_KO[c]} | {th[3:]} m² 이상 ({n}) | " + " | ".join(cells_) + " |")
    L += ["", "## 덩어리 크기별 성공 — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm) · 참값 점, 사전 정보마다 세 지역 합", "",
          "| 사전 정보 | 칸 | 덩어리 넓이 (m²) | 참값 점 | " + " | ".join(RES_KO[k] for k in ORDER) + " |", "|---|---|---|---:|" + "---|" * len(ORDER)]
    for u, d in out["sizebin"].items():
        if not u.startswith("합") or "method" not in d:
            continue
        pk = "LoD2" if u.endswith("LoD2") else "항공 LiDAR"
        r0 = next(iter(d["method"]))
        for c in d["method"][r0]:
            for b, x in d["method"][r0][c].items():
                if not x["rows"]:
                    continue
                cells_ = []
                for rk in ORDER:
                    R = mean_seeds(d, rk, lambda e: (e.get(c) or {}).get(b, {}).get("R_tau"))
                    M = mean_seeds(d, rk, lambda e: (e.get(c) or {}).get(b, {}).get("mean"))
                    cells_.append("—" if R is None else f"{100 * R:.1f} · {M:.1f}")
                L.append(f"| {pk} | {KEY_KO[c]} | {b} | {x['rows']:,}{'' if x['rows'] >= 10000 else '*'} | " + " | ".join(cells_) + " |")
    (DOCS / "tables/일6_덩어리.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
