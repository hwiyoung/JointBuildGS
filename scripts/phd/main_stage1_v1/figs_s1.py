"""PHD-MAIN-STAGE1-v1 figures of the results (jointbuildgs:dev, CPU; order 5.1). Methods that exist for a site are drawn; missing ones
are left blank with a note.

  python figs_s1.py discrim <site>      discrimination maps: per prior x method, the thinned GT points of the prior-error and observation-
                                        error regions coloured GT side / wrong side / both / neither (plan view, box u-v)
  python figs_s1.py sections            the sections of configs sections_v1.json: GT points, MVS points (box MVS), the registered priors and
                                        the results' meshes, points within 0.25 m of the plane
  python figs_s1.py curves              correction-rate curves per prior and method (pooled over the sites read so far), point counts per bin
scientific_verdict: null."""
import json
import sys

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

from s1_common import OUT, PREP, PRIOR_KO, SITES, Views, boxes, log, read_depth_bin, setup_fonts, xy_to_uv

plt = setup_fonts()
F = OUT / "figs"
METHODS = [("prop_{p}_s0", "본 방법 씨앗 0"), ("imgonly_s0", "영상만"), ("trust_{p}", "늘 믿음"), ("samepath_{p}", "사전 정보 그대로(같은 길)")]
CLS_COL = np.array([[0.17, 0.63, 0.17], [0.84, 0.15, 0.16], [1.0, 0.6, 0.0], [0.6, 0.6, 0.6]])
CLS_KO = ["참값 쪽", "틀린 자료 쪽", "둘 다", "둘 다 아님"]


def rows(site, prior):
    r = np.load(OUT / "defs" / site / f"rows_{prior}.npz")
    G = np.load(OUT / "defs" / site / "gt_classes.npz")
    X = {0: G["xyz_gt_points"].astype(np.float64)}
    if "xyz_gt_primary" in G.files:
        X[1] = G["xyz_gt_primary"].astype(np.float64)
    P = np.zeros((len(r["point"]), 3))
    for s, A in X.items():
        m = r["src"] == s
        P[m] = A[r["point"][m]]
    return r, P


def discrim(site):
    b = boxes()[SITES[site]]
    ms = [m for m in METHODS if not m[0].startswith("samepath")]
    fig, axs = plt.subplots(2, len(ms), figsize=(6.2 * len(ms), 11), constrained_layout=True, squeeze=False)
    for i, prior in enumerate(("LoD2", "ALS")):
        r, P = rows(site, prior)
        uv = xy_to_uv(P[:, :2])
        sel = r["thin"] & np.isin(r["code"], (11, 3)) & (np.abs(r["sW"]) >= 0.2)
        for j, (tmpl, lab) in enumerate(ms):
            ax = axs[i, j]
            res = tmpl.format(p=prior)
            f = OUT / "metrics" / site / f"{res}__{prior}_rows.npz"
            if not f.exists():
                ax.set_title(f"{PRIOR_KO[prior]} · {lab}: 결과 없음", fontsize=10)
                ax.set_axis_off()
                continue
            cls = np.load(f)["cls"]
            m = sel & (cls >= 0)
            ax.scatter(uv[m, 0], uv[m, 1], s=0.4, c=CLS_COL[cls[m]], marker="s", linewidths=0, rasterized=True)
            ax.plot([b["eval_u"][0], b["eval_u"][1], b["eval_u"][1], b["eval_u"][0], b["eval_u"][0]],
                    [b["eval_v"][0], b["eval_v"][0], b["eval_v"][1], b["eval_v"][1], b["eval_v"][0]], "k-", lw=0.6)
            ax.set_aspect("equal")
            sh = [100 * float((cls[m] == k).mean()) if m.any() else 0 for k in range(4)]
            ax.set_title(f"{PRIOR_KO[prior]} · {lab} — 참값 쪽 {sh[0]:.0f} %, 틀린 쪽 {sh[1]:.0f} %, 둘 다 {sh[2]:.0f} %", fontsize=10)
            ax.set_xticks([])
            ax.set_yticks([])
    fig.legend(handles=[Line2D([], [], marker="s", ls="", color=CLS_COL[k], label=CLS_KO[k], markersize=9) for k in range(4)], loc="lower center", ncol=4,
               fontsize=11, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle(f"{site} 판별 지도 — 사전 정보 오류 영역과 관측 오류 영역의 솎은 참값 점(|W − 참값| ≥ 0.2 m)이 결과 메시에서 어느 쪽에 있는가", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / f"discrim_{site}.png", dpi=80, bbox_inches="tight")
    plt.close(fig)


def plane_segments(V, Fc, c, t, L):
    npn = np.array([-t[1], t[0], 0.0])
    d = (V - c) @ npn
    dt = d[Fc]
    cross = (dt.min(1) < 0) & (dt.max(1) > 0)
    F_, d_ = Fc[cross], dt[cross]
    ms, Xs = [], []
    for a, b_ in ((0, 1), (1, 2), (2, 0)):
        m = (d_[:, a] < 0) != (d_[:, b_] < 0)
        w = d_[:, a] / np.where(m, d_[:, a] - d_[:, b_], 1.0)
        ms.append(m)
        Xs.append(V[F_[:, a]] + w[:, None] * (V[F_[:, b_]] - V[F_[:, a]]))
    ms = np.stack(ms, 1)
    Xs = np.stack(Xs, 1)
    ok = ms.sum(1) == 2
    idx = np.argsort(~ms[ok], axis=1, kind="stable")[:, :2]
    X2 = np.take_along_axis(Xs[ok], idx[:, :, None].repeat(3, 2), 1)
    sv = (X2[..., :2] - c[:2]) @ t[:2]
    seg = np.stack([sv, X2[..., 2]], -1)
    return seg[np.abs(sv).min(1) <= L]


def sections():
    import open3d as o3d
    from metrics_s1 import result_paths
    S = json.loads((OUT / "defs/sections_v1.json").read_text())["sections"]
    V = Views()
    names = list(S)
    fig, axs = plt.subplots(len(names), 1, figsize=(15, 4.8 * len(names)), constrained_layout=True)
    cols = {"prop": "#1f77b4", "imgonly": "#ff7f0e", "trust": "#8c564b", "samepath": "#7f7f7f", "prop_other": "#9467bd"}
    for k, nm in enumerate(names):
        s = S[nm]
        ax = axs[k]
        site, prior = s["site"], s["prior"]
        c, t, L = np.asarray(s["centre"]), np.asarray(s["t"]), float(s["L"]) / 2
        npn = np.array([-t[1], t[0], 0.0])
        G = np.load(OUT / "defs" / site / "gt_classes.npz")
        X = G["xyz_gt_primary" if (site.startswith("B0") and "xyz_gt_primary" in G.files) else "xyz_gt_points"].astype(np.float64)
        near = (np.abs((X - c) @ npn) <= 0.25) & (np.abs((X[:, :2] - c[:2]) @ t) <= L) & (np.abs(X[:, 2] - c[2]) <= 6)
        ax.scatter((X[near] - c)[:, :2] @ t, X[near, 2], s=1.0, c="k", label=f"참값 점 {int(near.sum()):,}", zorder=3)
        mv = PREP / "mvs" / f"box_{site}" / "stereo/depth_maps"
        Mv = []
        for f in sorted(mv.glob("*.geometric.bin")):
            n = f.name[: -len(".geometric.bin")]
            d = read_depth_bin(f)
            ok = np.isfinite(d) & (d > 0)
            P = V.C(n)[None, :] + d[ok][:, None].astype(np.float64) * V.rays(n, np.float64)[ok]
            m = (np.abs((P - c) @ npn) <= 0.25) & (np.abs((P[:, :2] - c[:2]) @ t) <= L) & (np.abs(P[:, 2] - c[2]) <= 6)
            Mv.append(P[m])
        Mv = np.concatenate(Mv) if Mv else np.zeros((0, 3))
        ax.scatter((Mv - c)[:, :2] @ t, Mv[:, 2], s=0.5, c="#ff7f0e", alpha=0.4, label=f"MVS 점 {len(Mv):,}", zorder=2)
        for p, col in (("LoD2", "#d62728"), ("ALS", "#2ca02c")):
            pr = np.load(OUT / "defs" / site / f"prior_{p}.npz")
            ax.add_collection(LineCollection(plane_segments(pr["V"], pr["F"], c, t, L), colors=col, linewidths=2.0, label=f"사전 정보 {PRIOR_KO[p]}", zorder=1))
        other = "ALS" if prior == "LoD2" else "LoD2"
        for res, lab, col in ((f"prop_{prior}_s0", f"본 방법 {PRIOR_KO[prior]} 씨앗 0", cols["prop"]), (f"prop_{other}_s0", f"본 방법 {PRIOR_KO[other]} 씨앗 0", cols["prop_other"]),
                              ("imgonly_s0", "영상만", cols["imgonly"]), (f"trust_{prior}", f"늘 믿음 {PRIOR_KO[prior]}", cols["trust"])):
            pth = result_paths(site, res).get("mesh")
            if pth is None or not pth.exists():
                continue
            m = o3d.io.read_triangle_mesh(str(pth))
            Vr, Fr = np.asarray(m.vertices), np.asarray(m.triangles)
            nr = (np.abs((Vr - c) @ npn) <= 1.0) & (np.abs((Vr[:, :2] - c[:2]) @ t) <= L + 1)
            ax.add_collection(LineCollection(plane_segments(Vr, Fr[nr[Fr].any(1)], c, t, L), colors=col, linewidths=1.0, label=lab, zorder=4))
        ax.set_xlim(-L, L)
        ax.set_ylim(c[2] - 4.0, c[2] + 4.0)
        ax.set_title(f"{nm} ({site}, {s['why']}; 패치 {s['patch']}, 참값 − {PRIOR_KO[prior]} {100 * s['gt_med']:+.0f} cm)", fontsize=10)
        ax.set_xlabel("단면 방향 거리 (m)")
        ax.set_ylabel("z (m)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="upper right", ncol=4, markerscale=6)
    fig.suptitle("단면(학습 결과를 보기 전에 규칙으로 고른 자리, ±0.25 m 안의 점)", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / "sections_s1.png", dpi=80)
    plt.close(fig)


def curves():
    fig, axs = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    for ax, prior in zip(axs, ("LoD2", "ALS")):
        for tmpl, lab in METHODS:
            pts, rates = {}, {}
            for site in SITES:
                f = OUT / "metrics" / site / f"{tmpl.format(p=prior)}__{prior}_rows.npz"
                if not f.exists():
                    continue
                rr = np.load(f)
                r, _ = rows(site, prior)
                cls = rr["cls"]
                m = r["thin"] & (r["code"] == 11) & (np.abs(r["sW"]) >= 0.2) & (cls >= 0)
                ratio = np.abs(r["sW"][m]) / r["tau"][m]
                for lo, hi in ((1, 1.5), (1.5, 2), (2, 3), (3, 4), (4, 8), (8, np.inf)):
                    mb = (ratio >= lo) & (ratio < hi)
                    pts[lo] = pts.get(lo, 0) + int(mb.sum())
                    rates[lo] = rates.get(lo, 0) + int((cls[m][mb] == 0).sum())
            if not pts:
                continue
            xs = sorted(pts)
            ys = [100 * rates[x] / pts[x] if pts[x] else np.nan for x in xs]
            ax.plot(range(len(xs)), ys, "o-", label=f"{lab} (점 {sum(pts.values()):,})")
            for i, x in enumerate(xs):
                ax.annotate(f"{pts[x]:,}", (i, ys[i]), fontsize=6, xytext=(2, 4), textcoords="offset points")
        ax.set_xticks(range(6))
        ax.set_xticklabels(["1~1.5τ", "1.5~2τ", "2~3τ", "3~4τ", "4~8τ", "8τ 넘게"])
        ax.set_ylim(-5, 105)
        ax.axhline(50, color="k", lw=0.6, ls="--")
        ax.set_ylabel("보정률 (참값 쪽 %)")
        ax.set_title(f"{PRIOR_KO[prior]}: 어긋남 크기별 보정률 (지역을 합침, 솎은 점)", fontsize=11)
        ax.legend(fontsize=8)
    fig.savefig(F / "curves_s1.png", dpi=85)
    plt.close(fig)


if __name__ == "__main__":
    a = sys.argv[1:]
    {"discrim": lambda: discrim(a[1]), "sections": sections, "curves": curves}[a[0]]()
    log("figure", a)
