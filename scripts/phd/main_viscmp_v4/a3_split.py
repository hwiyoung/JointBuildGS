"""PHD-MAIN-VISCMP-v4 일 다: the precision split by the slope of the result surface and the relation to the GT.
The result sample of the distance task is regenerated with its own rule (dm_common.result_sample: triangles with the centroid in a
building-surface cell or > 0.01 m2, 400 points per m2, seed 0, the points inside the cells) keeping each point's triangle, checked against
the stored sample (the number of points = len(q_d) of the case's distance file; d_r recomputed for 2,000 points = q_d). Per point:
slope = the angle between its triangle's normal and the vertical; relation by d_r (q_d; B0's place 두 자료가 모두 맞는 곳 reads q_d_b0gt as
the distance task); excluded = the GT exclusion cell (exclusion_cells.npz 'any') at its plan position. Places: 전체, c2.
For 일 라 the samples of the figure's cases (B0 ALS, B173 주변 ALS and LoD2; 학습 전 사전 정보, 결합, 본 방법 씨앗 0) are kept in /vc/work.
  python a3_split.py [site]   -> /vc/work/split_<site>.json (+ samples), then python a3_split.py --tables -> /docs/tables/precision_split.*
scientific_verdict: null"""
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

import vc_common  # noqa: F401
from dm_common import DIST, METHODS, PLACES, SiteGT, case_ko, read_mesh, results_of
from src.phd.metrics_v3 import cloud
from vc_common import CFG, DOCS, S1, VC, jdump, jl, log, now

BITS = {k: 1 << i for i, k in enumerate(PLACES[1:])}
KEEP = {("B0_b10", "ALS"), ("B173nb_b10", "ALS"), ("B173nb_b10", "LoD2")}
KEEP_RES = {"samepath", "mvsfuse", "prop_"}


def sample_with_tri(V, F, gt):
    """dm_common.result_sample with the triangle index of every point (the same random stream)."""
    tri_in = np.zeros(len(F), bool)
    for b in range(0, len(F), 4_000_000):
        T3 = V[F[b:b + 4_000_000]]
        tri_in[b:b + 4_000_000] = gt.in_cells(T3.mean(1)) | (0.5 * np.linalg.norm(np.cross(T3[:, 1] - T3[:, 0], T3[:, 2] - T3[:, 0]), axis=1) > 0.01)
        del T3
    Fi = np.nonzero(tri_in)[0]
    Fs = np.asarray(F[Fi], np.int64); Vd = np.asarray(V, np.float64)
    A = cloud.tri_areas(Vd, Fs)
    n = int(round(A.sum() * 400))
    rng = np.random.default_rng(0)
    cs = np.cumsum(A)
    tri = np.minimum(np.searchsorted(cs, rng.random(n) * cs[-1], side="right"), len(Fs) - 1)
    r1 = np.sqrt(rng.random(n))[:, None]; r2 = rng.random(n)[:, None]
    f = Fs[tri]
    smp = (1 - r1) * Vd[f[:, 0]] + r1 * (1 - r2) * Vd[f[:, 1]] + r1 * r2 * Vd[f[:, 2]]
    keep = gt.in_cells(smp)
    t = Fi[tri[keep]]
    N = np.cross(Vd[F[t, 1]] - Vd[F[t, 0]], Vd[F[t, 2]] - Vd[F[t, 0]])
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return smp[keep], np.degrees(np.arccos(np.clip(np.abs(N[:, 2]), 0, 1)))


def excl_lookup(site):
    e = np.load(S1 / "v3/box_gt" / site / "exclusion_cells.npz")
    e0, n0, res = 690700.0, 5335820.0, 0.5
    ny, nx = e["any"].shape

    def f(X, key="any"):
        ix = np.floor((X[:, 0] + 690953.0 - e0) / res).astype(np.int64); iy = np.floor((X[:, 1] + 5336071.0 - n0) / res).astype(np.int64)
        ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
        out = np.zeros(len(X), bool)
        out[ok] = e[key][iy[ok], ix[ok]]
        return out
    return f, e


def stats(slope, dr, ex, C):
    W = C["work_da"]; out = {}
    rb = W["relation_bins_m"]
    for (a, b), nm in zip(W["slope_bins_deg"], W["slope_names"]):
        m = (slope >= a) & ((slope < b) if b < 90 else (slope <= 90.0001))
        n = int(m.sum()); d = dr[m]
        out[nm] = dict(n=n, share=float(m.mean()) if len(m) else None, P_0_2=float((d <= 0.2).mean()) if n else None,
                       rel=[float((d <= rb[0]).mean()) if n else None, float(((d > rb[0]) & (d <= rb[1])).mean()) if n else None, float((d > rb[1]).mean()) if n else None],
                       excluded=float(ex[m].mean()) if n else None)
    out["모두"] = dict(n=int(len(dr)), P_0_2=float((dr <= 0.2).mean()) if len(dr) else None, excluded=float(ex.mean()) if len(dr) else None,
                       rel=[float((dr <= rb[0]).mean()), float(((dr > rb[0]) & (dr <= rb[1])).mean()), float((dr > rb[1]).mean())] if len(dr) else None)
    return out


def run_site(site):
    t0 = time.time()
    C = jl(CFG); gt = SiteGT(site); exf, _ = excl_lookup(site)
    tree = cKDTree(gt.Gb)
    res_cases = {}
    for prior in ("LoD2", "ALS"):
        for m in METHODS:
            for r in results_of(m, prior):
                res_cases.setdefault(r, []).append(prior)
    out = dict(site=site, made=now(), results={}, scientific_verdict=None)
    for r, priors in res_cases.items():
        f0 = DIST / f"{site}_{priors[0]}__{r}.npz"
        j0 = jl(DIST / f"{site}_{priors[0]}__{r}.json") or {}
        if not f0.exists() or not j0.get("mesh"):
            out["results"][r] = dict(status="결과 없음"); log(site, r, "no result"); continue
        mp = vc_common.resolve(j0["mesh"])
        t1 = time.time()
        V, F = read_mesh(mp)
        smp, slope = sample_with_tri(V, F, gt)
        del V, F
        ex = exf(smp)
        rec = dict(mesh=str(mp), points=int(len(smp)), seconds_sample=round(time.time() - t1, 1), cases={})
        for prior in priors:
            z = np.load(DIST / f"{site}_{prior}__{r}.npz")
            same = len(z["q_d"]) == len(smp)
            chk = None
            if same:
                ii = np.random.default_rng(1).choice(len(smp), size=min(2000, len(smp)), replace=False)
                chk = float(np.max(np.abs(tree.query(smp[ii], workers=-1)[0] - z["q_d"][ii])))
            rec["cases"][prior] = dict(sample_matches=bool(same), stored_points=int(len(z["q_d"])), max_abs_dr_diff_2000=chk)
            if not same or chk is None or chk > 1e-4:
                rec["cases"][prior]["status"] = "표본이 저장된 것과 다름"; log(site, r, prior, "SAMPLE MISMATCH", len(smp), len(z["q_d"]), chk); continue
            dr = z["q_d"].astype(np.float64)
            fb = DIST / f"{site}_{prior}__{r}__b0gt.npz"
            dr_pl = np.load(fb)["q_d_b0gt"].astype(np.float64) if (site == "B0_b10" and fb.exists()) else dr
            c2 = (z["q_place"] & BITS["c2"]) > 0
            rec["cases"][prior].update(status="있음", all=stats(slope, dr, ex, C), c2=stats(slope[c2], dr_pl[c2], ex[c2], C))
            if (site, prior) in KEEP and (r.startswith("samepath") or r.startswith("mvsfuse") or r == f"prop_{prior}_s0"):
                np.savez_compressed(VC / "work" / f"sample_{site}_{prior}__{r}.npz", xyz=smp.astype(np.float32), dr=dr.astype(np.float32), excl=ex, slope=slope.astype(np.float16))
        out["results"][r] = rec
        log(site, r, len(smp), rec["seconds_sample"], {p: rec["cases"][p].get("status") for p in priors})
    out["seconds"] = round(time.time() - t0, 1)
    jdump(VC / "work" / f"split_{site}.json", out)


def excluded_desc(site):
    _, e = excl_lookup(site)
    import s1_common as DS
    bx = DS.boxes()[DS.SITES[site]]
    ny, nx = e["any"].shape
    iy, ix = np.mgrid[0:ny, 0:nx]
    X = np.column_stack([(ix.ravel() + 0.5) * 0.5 + 690700.0 - 690953.0, (iy.ravel() + 0.5) * 0.5 + 5335820.0 - 5336071.0, np.zeros(ix.size)])
    inr = DS.in_eval_uv(X, bx)
    d = {}
    for k, ko in (("trees", "나무"), ("transient", "일시 물체"), ("prior_side_trees", "사전 정보 쪽 나무(항공 LiDAR) — 따로 기록된 갈래, 참값에서 빼지 않음"), ("any", "참값에서 뺀 칸 = 나무 ∪ 일시 물체")):
        c = int((e[k].ravel() & inr).sum())
        d[k] = dict(name=ko, cells_in_range=c, area_m2=c * 0.25)
    return d


def tables():
    C = jl(CFG); W = C["work_da"]
    cases = [(s, p) for s in ("B0_b10", "B173nb_b10", "R1rep_b10") for p in ("LoD2", "ALS")]
    order = [("prior", "학습 전 사전 정보"), ("twodgs", "2DGS"), ("geogs", "GeoGS"), ("mvsfuse", "결합"), ("cdgs", "CDGS"), ("method_s0", "본 방법 씨앗 0"), ("method_s1", "본 방법 씨앗 1"), ("method", "본 방법(평균)")]
    S = {s: jl(VC / "work" / f"split_{s}.json") for s in ("B0_b10", "B173nb_b10", "R1rep_b10")}
    data, L = {}, ["# 정밀도를 나누어 셈 — 일 다 [이 발주에서 냄]", "", f"- 만든 때 {now()}. 결과 점 = 새 거리 지표의 결과 표본(1 m²당 400점, 씨앗 0)을 같은 규칙으로 다시 뽑은 것(저장된 표본과 점 수와 d_r이 같음을 확인). 기울기 = 그 점이 놓인 삼각형 법선과 연직축의 각.",
                   "- 관계: 가까움 d_r ≤ 0.2 m, '1 m 안' 0.2 < d_r ≤ 1.0 m, '1 m 밖' d_r > 1.0 m. 뺀 칸 = 참값에서 뺀 0.5 m 칸('any' = 나무 ∪ 일시 물체; gt_classes.npz의 excl_gt_points와 점마다 같음)에 든 결과 점의 몫. [고침 10-21 16:44: 처음 판은 '사전 정보 쪽 나무'도 든다고 적었으나 'any'에 들지 않는다. 값은 처음부터 'any'로 셈]",
                   "- 결과 표본은 새 거리 지표의 참값 칸(건물 면 칸, 뺀 칸 밖) 안에서만 뽑히므로, 뺀 칸에 든 몫은 모든 칸에서 0이다.",
                   "- 몫 = 그 곳의 결과 점 가운데 그 기울기 구간의 몫. `*` = 표본 1만 점 미만, '표본 부족' = 100점 미만. 본 방법(평균) = 두 씨앗 값의 평균.", ""]
    for site, prior in cases:
        u = f"{site}/{prior}"; data[u] = {}
        for k, nm in order:
            if k == "method":
                a, b = data[u].get("method_s0"), data[u].get("method_s1")
                data[u][k] = None if not a or not b else {pl: {sb: {kk: (None if a[pl][sb].get(kk) is None else
                                                                        ([0.5 * (x + y) for x, y in zip(a[pl][sb][kk], b[pl][sb][kk])] if isinstance(a[pl][sb][kk], list) else
                                                                         (min(a[pl][sb][kk], b[pl][sb][kk]) if kk == "n" else 0.5 * (a[pl][sb][kk] + b[pl][sb][kk]))))
                                                                   for kk in a[pl][sb]} for sb in a[pl]} for pl in a}
                continue
            mk = {"method_s0": "method", "method_s1": "method"}.get(k, k)
            res = results_of(mk, prior)[1 if k == "method_s1" else 0]
            e = S[site]["results"].get(res, {})
            c = (e.get("cases") or {}).get(prior, {})
            data[u][k] = {pl: c[pl] for pl in ("all", "c2")} if c.get("status") == "있음" else None
        for pl, plko in (("all", "전체"), ("c2", "두 자료가 모두 맞는 곳")):
            L += [f"## {case_ko(site, prior)} · {plko}", "", "| 결과 | 구간 | 몫 | 정밀도 | 가까움 | 1 m 안 | 1 m 밖 | 뺀 칸 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
            for k, nm in order:
                d = data[u][k]
                if d is None:
                    L.append(f"| {nm} | — | 결과 없음 | | | | | |"); continue
                for sb in W["slope_names"] + ["모두"]:
                    x = d[pl][sb]; n = x.get("n", 0)
                    if not n or n < 100:
                        L.append(f"| {nm} | {sb} | 표본 부족 | | | | | |"); continue
                    st = "*" if n < 10000 else ""
                    sh = "100.0" if sb == "모두" else f"{100 * x['share']:.1f}"
                    L.append(f"| {nm} | {sb} | {sh}{st} | {100 * x['P_0_2']:.1f} | {100 * x['rel'][0]:.1f} | {100 * x['rel'][1]:.1f} | {100 * x['rel'][2]:.1f} | {100 * x['excluded']:.1f} |")
            L.append("")
    desc = {s: excluded_desc(s) for s in ("B0_b10", "B173nb_b10", "R1rep_b10")}
    L += ["## 참값에서 뺀 칸", "", "| 지역 | 갈래 | 칸 수(평가 범위) | 넓이 (m²) |", "|---|---|---:|---:|"]
    for s, d in desc.items():
        for k, v in d.items():
            L.append(f"| {s.split('_')[0]} | {v['name']} | {v['cells_in_range']:,} | {v['area_m2']:,.1f} |")
    L += ["", "- 규칙: `scripts/phd/main_stage1_v1/s04_gt_v7.py`(나무, 일시 물체, 사전 정보 쪽 나무를 결과 전에 정함), `defs_s1.py`(평가 범위 안 참값 = 범위 안 & 뺀 칸 밖). 지역마다 하나의 판(두 사전 정보가 함께 씀)이다."]
    jdump(DOCS / "tables/precision_split.json", dict(task="PHD-MAIN-VISCMP-v4", work="일 다", made=now(), data=data, excluded_cells=desc,
                                                     checks={s: {r: e.get("cases") for r, e in S[s]["results"].items()} for s in S}, scientific_verdict=None))
    (DOCS / "tables/precision_split.md").write_text("\n".join(L) + "\n")
    log("tables done")


if __name__ == "__main__":
    if sys.argv[1] == "--tables":
        tables()
    else:
        run_site(sys.argv[1])
