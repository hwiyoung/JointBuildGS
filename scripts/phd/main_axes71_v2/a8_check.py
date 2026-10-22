"""PHD-MAIN-AXES71-v2 일 8 (11.1): the check of the result-side distance (jointbuildgs:dev, CPU).

  python a8_check.py   -> AX/tables/a8_check.json, /docs/tables/일8_결과기준점검.md|json, /docs/figures/일8_단면_B0_항공LiDAR_벽.png|pdf|json

(1) Density: every result point takes the GT density of its nearest prior patch (일 1; the patch's GT rows / area). Bins = the case's five
quantiles of the density of the in-range patches with GT (common to every result) + '참값 행 없음'. Per bin, count (셈 가: d_r; 셈 마:
normal distance, lateral <= 0.5 m) and result: share of the counted result points over 1 m, the counted points and the share not counted.
The GT of the places is used (B0: ULS + primary GT, as the density). (2) The input prior (학습 전 사전 정보): the result-side values by
the slope of the nearest patch (0~30, 30~60, 60~90 deg) for 셈 가-바: P(τ), mean, median, share not counted. (3) A horizontal section
through one long wall of B0 · 항공 LiDAR: the wall = the largest clump of in-range prior patches steeper than 60 deg (6.3 deg tolerance on
the normal direction, linked within 0.36 m), chosen from the prior patches and the GT only; the section height = the median height of the
wall patches; slab +-0.05 m. Panels: 학습 전 사전 정보, 결합, 본 방법 (seed 0) x colour by d_r / by 셈 마. [이 발주에서 냄]
scientific_verdict: null."""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

import ax_map as MP
from ax_common import CASES, CFG, DIST, DOCS, ORDER, RES_KO, SITES, TAB, case_ko, jdump, log, now, results_of
from ax_arrays import arrays, cells, res_vals

SLOPES = CFG["check_res"]["slope_bins_deg"]


def density_bins(C):
    dens = C["density"].astype(np.float64)
    ok = (C["cell"] >= 0) & C["has_gt"]
    q = np.percentile(dens[ok], [20, 40, 60, 80])
    return np.concatenate([[0.0], q, [np.inf]])


def part1(site, prior, A, C, edges):
    s = A["smp"]
    dens = C["density"].astype(np.float64)[s["patch"]]
    has = C["has_gt"][s["patch"]]
    out = {}
    for c in ("A", "E"):
        d, ok = res_vals(s, c, True)
        rows = []
        for i in range(5):
            m = has & (dens >= edges[i]) & (dens < edges[i + 1])
            k = m & ok
            rows.append(dict(bin=i, lo=float(edges[i]), hi=float(edges[i + 1]), n=int(k.sum()), not_counted=float((m & ~ok).sum() / max(m.sum(), 1)),
                             over1=float((d[k] > 1.0).mean()) if k.any() else None))
        m = ~has
        k = m & ok
        rows.append(dict(bin="참값 행 없음", n=int(k.sum()), not_counted=float((m & ~ok).sum() / max(m.sum(), 1)), over1=float((d[k] > 1.0).mean()) if k.any() else None))
        out[c] = rows
    return out


def part2(A, C):
    s = A["smp"]
    sl = C["slope"].astype(np.float64)[s["patch"]]
    out = {}
    for i in range(len(SLOPES) - 1):
        m = (sl >= SLOPES[i]) & (sl < SLOPES[i + 1] + (1e-6 if i == len(SLOPES) - 2 else 0))
        e = {}
        for c in "ABCDEF":
            d, ok = res_vals(s, c, True)
            k = m & ok
            e[c] = dict(n_all=int(m.sum()), n=int(k.sum()), not_counted=float((m & ~ok).sum() / max(m.sum(), 1)),
                        P_tau=float((d[k] <= s["tau"][k]).mean()) if k.any() else None, mean=float(d[k].mean() * 100) if k.any() else None,
                        med=float(np.median(d[k]) * 100) if k.any() else None)
        out[f"{SLOPES[i]}-{SLOPES[i + 1]}"] = e
    return out


def pick_wall(site, prior, C):
    """the largest clump of steep in-range prior patches with one facing (from the prior and the GT only)."""
    R = np.load(f"/out/regions_v3/regions_ext_v3_{site}_{prior}.npz")
    U = np.load(MP.S0U.format(site=site, prior=prior))
    n = np.cross(U["loc_t1"], U["loc_t2"]); n /= np.linalg.norm(n, axis=1, keepdims=True)
    cen = R["centre"].astype(np.float64)
    steep = (C["cell"] >= 0) & (C["slope"] > 60) & C["has_gt"]
    idx = np.nonzero(steep)[0]
    pr = cKDTree(cen[idx]).query_pairs(0.36, output_type="ndarray")
    if len(pr):
        same = np.abs((n[idx[pr[:, 0]]] * n[idx[pr[:, 1]]]).sum(1)) > np.cos(np.radians(6.3))
        pr = pr[same]
    G = coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), shape=(len(idx), len(idx)))
    k, lab = connected_components(G, directed=False)
    big = np.bincount(lab).argmax()
    w = idx[lab == big]
    return w, cen[w], n[w]


def section(site, prior):
    C = cells(site, prior)
    w, cw, nw = pick_wall(site, prior, C)
    z0 = float(np.median(cw[:, 2]))
    lo, hi = cw[:, :2].min(0) - 3.0, cw[:, :2].max(0) + 3.0
    from ax_common import SiteGT
    gt = SiteGT(site)
    G = np.vstack([gt.Gb, gt.X[1][gt.G["use_gt_primary"].astype(bool)]]) if 1 in gt.X else gt.Gb
    sl = (np.abs(G[:, 2] - z0) < 0.05) & np.all((G[:, :2] >= lo) & (G[:, :2] <= hi), 1)
    pan = {}
    for rk in ("prior", "mvsfuse", "method"):
        res = results_of(rk, prior)[0]
        X = np.load(DIST / f"{site}__{res}__xyz.npy").astype(np.float64)
        A = arrays(site, prior, res, C)
        s = A["smp"]
        m = (np.abs(X[:, 2] - z0) < 0.05) & np.all((X[:, :2] >= lo) & (X[:, :2] <= hi), 1)
        dA, _ = res_vals(s, "A", True)
        dE, okE = res_vals(s, "E", True)
        pan[rk] = dict(xy=X[m, :2], dA=dA[m], dE=dE[m], okE=okE[m], tau=s["tau"][m], res=res)
    return dict(z0=z0, lo=lo, hi=hi, gt=G[sl, :2], wall_patches=int(len(w)), wall_area=float(C["area"][w].sum()), panels=pan)


def fig_section(S):
    plt = MP.setup_plt()
    cols = {"near": "#9e9e9e", "mid": "#f28e2b", "far": "#d62728", "undec": "#7ec8e3"}
    fig, axs = plt.subplots(2, 3, figsize=(17 / 2.54, 11 / 2.54), sharex=True, sharey=True)
    vals = {}
    for j, rk in enumerate(("prior", "mvsfuse", "method")):
        p = S["panels"][rk]
        for i, (key, nm) in enumerate((("dA", "가장 가까운 참값 점까지 (셈 가)"), ("dE", "참값 면까지 법선 방향 (셈 마)"))):
            ax = axs[i, j]
            ax.scatter(S["gt"][:, 0], S["gt"][:, 1], s=0.3, c="k", lw=0, rasterized=True)
            d = p[key]
            ok = p["okE"] if key == "dE" else np.ones(len(d), bool)
            c = np.where(d <= p["tau"], 0, np.where(d <= 1.0, 1, 2))
            for k_, cc in ((0, cols["near"]), (1, cols["mid"]), (2, cols["far"])):
                m = ok & (c == k_)
                ax.scatter(p["xy"][m, 0], p["xy"][m, 1], s=0.6, c=cc, lw=0, rasterized=True)
            if key == "dE":
                ax.scatter(p["xy"][~ok, 0], p["xy"][~ok, 1], s=0.6, c=cols["undec"], lw=0, rasterized=True)
            ax.set_aspect("equal"); ax.tick_params(labelsize=5, length=2)
            if i == 0:
                ax.set_title(RES_KO[rk], fontsize=7)
            if j == 0:
                ax.set_ylabel(nm, fontsize=6)
            n = len(d)
            vals.setdefault(rk, {})[key] = dict(points=int(n), share_le_tau=float(((d <= p["tau"]) & ok).sum() / max(n, 1)), share_tau_1m=float(((d > p["tau"]) & (d <= 1) & ok).sum() / max(n, 1)),
                                                share_over_1m=float(((d > 1) & ok).sum() / max(n, 1)), not_counted=float((~ok).sum() / max(n, 1)))
    from matplotlib.lines import Line2D
    hs = [Line2D([0], [0], marker="o", ls="none", color=c, ms=4, label=l) for c, l in ((cols["near"], "τ 안"), (cols["mid"], "τ~1 m"), (cols["far"], "1 m 넘음"),
                                                                                     (cols["undec"], "판단할 수 없음 (셈 마)"), ("k", "참값 점"))]
    fig.legend(handles=hs, loc="lower center", ncol=5, fontsize=6, frameon=False)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    stem = DOCS / "figures/일8_단면_B0_항공LiDAR_벽"
    for e in ("png", "pdf"):
        fig.savefig(f"{stem}.{e}", dpi=300)
    plt.close(fig)
    jdump(f"{stem}.json", dict(task="PHD-MAIN-AXES71-v2", work="일 8 단면", made=now(), z0=S["z0"], window=[S["lo"].tolist(), S["hi"].tolist()], slab_m=0.05,
                               wall_patches=S["wall_patches"], wall_area_m2=S["wall_area"], gt_points=int(len(S["gt"])), values=vals,
                               rule=__doc__.split("\n\n")[1].split("(3)")[1], scientific_verdict=None))
    return vals


def main():
    out = dict(density={}, prior_slope={})
    for site, prior in CASES:
        u = f"{site}/{prior}"
        C = cells(site, prior)
        edges = density_bins(C)
        out["density"][u] = dict(edges=edges.tolist(), results={})
        for rk in ORDER:
            for res in results_of(rk, prior)[:1]:
                A = arrays(site, prior, res, C)
                if A.get("status") != "있음":
                    out["density"][u]["results"][rk] = dict(status=A.get("status"))
                    continue
                out["density"][u]["results"][rk] = part1(site, prior, A, C, edges)
                if rk == "prior":
                    out["prior_slope"][u] = part2(A, C)
        log(u)
    S = section("B0_b10", "ALS")
    out["section"] = fig_section(S)
    jdump(TAB / "a8_check.json", dict(task="PHD-MAIN-AXES71-v2", work="일 8", made=now(), rule=__doc__.split("\n\n")[1], data=out, scientific_verdict=None))
    jdump(DOCS / "tables/일8_결과기준점검.json", jl_safe(TAB / "a8_check.json"))
    L = ["# 일 8 결과 기준 거리의 점검 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]", "", f"- 만든 때 {now()}. 결과 점의 참값 밀도 = 가장 가까운 사전 정보 패치의 참값 밀도(일 1). 구간 = 경우마다 참값 있는 평가 범위 패치 밀도의 다섯 분위(모든 결과 공통). "
         "칸 = 1 m 넘는 결과 점 (%) (셈 마에서 판단할 수 없는 점 %). 본 방법은 씨앗 0. 해석은 쓰지 않음.", ""]
    for u, d in out["density"].items():
        e = d["edges"]
        labs = [f"{e[i]:.0f}~{e[i + 1]:.0f}" if np.isfinite(e[i + 1]) else f"{e[i]:.0f}~" for i in range(5)] + ["참값 행 없음"]
        L += [f"## {case_ko(*u.split('/'))}", "", "| 결과 | 셈 | " + " | ".join(f"밀도 {l} 점/m²" if l != '참값 행 없음' else l for l in labs) + " |", "|---|---|" + "---|" * 6]
        for rk in ORDER:
            r = d["results"].get(rk, {})
            if "A" not in r:
                L.append(f"| {RES_KO[rk]} | — | {r.get('status', '결과 없음')} |" + " |" * 5)
                continue
            for c, cn in (("A", "가"), ("E", "마")):
                cs = []
                for x in r[c]:
                    if x["over1"] is None:
                        cs.append("—")
                    else:
                        cs.append(f"{100 * x['over1']:.1f}" + (f" ({100 * x['not_counted']:.1f})" if c == "E" else "") + ("*" if x["n"] < 10000 else ""))
                L.append(f"| {RES_KO[rk]} | {cn} | " + " | ".join(cs) + " |")
        L.append("")
    L += ["## 학습 전 사전 정보의 결과 기준 값 — 기울기 구간별", "", "- 칸 = P(τ) (%) · 평균 (cm) · 중앙값 (cm) · 세지 않은 점 (%).", "",
          "| 경우 | 기울기 (°) | " + " | ".join(f"셈 {x}" for x in "가나다라마바") + " |", "|---|---|" + "---|" * 6]
    for u, d in out["prior_slope"].items():
        for b, e in d.items():
            cs = []
            for c in "ABCDEF":
                x = e[c]
                cs.append("—" if x["P_tau"] is None else f"{100 * x['P_tau']:.1f} · {x['mean']:.1f} · {x['med']:.1f} · {100 * x['not_counted']:.1f}" + ("*" if x["n"] < 10000 else ""))
            L.append(f"| {case_ko(*u.split('/'))} | {b} | " + " | ".join(cs) + " |")
    L += ["", "## B0 · 항공 LiDAR 긴 벽의 수평 단면 (그림 일8_단면_B0_항공LiDAR_벽)", "", "| 결과 | 칠한 거리 | 단면의 결과 점 | τ 안 (%) | τ~1 m (%) | 1 m 넘음 (%) | 판단할 수 없음 (%) |", "|---|---|---:|---:|---:|---:|---:|"]
    for rk, v in out["section"].items():
        for key, nm in (("dA", "셈 가"), ("dE", "셈 마")):
            x = v[key]
            L.append(f"| {RES_KO[rk]} | {nm} | {x['points']:,} | {100 * x['share_le_tau']:.1f} | {100 * x['share_tau_1m']:.1f} | {100 * x['share_over_1m']:.1f} | {100 * x['not_counted']:.1f} |")
    (DOCS / "tables/일8_결과기준점검.md").write_text("\n".join(L) + "\n")


def jl_safe(p):
    import json
    return json.loads(open(p).read())


if __name__ == "__main__":
    main()
