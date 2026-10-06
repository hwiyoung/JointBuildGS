"""PHD-MAIN-METRICS-TRIAL-v1 4.6 figures (jointbuildgs:dev, CPU; Open3D ray casting). Views and sections come from defs/
(fixed before the metrics); the region maps are made by regions_ext_v1.py.

  python figs_mt.py [names ...]     default: all

spread_map      plan view of B173 and neighbours: GT rows of the spread regions coloured by class (GT side, wrong side, both,
                neither), the four trainings and both prior as-is (surface, same path)
size_curve      GT-side share per size bin, both seeds per prior; lines at tau, the conflict threshold and 4 tau
size_sections   one representative section per bin and prior (defs/sections.json): prior, both seeds, GT points
height_map      z_result - z_GT of the accuracy roof points (+-0.5 m), edge band grey; trainings and prior as-is
bias_paths      the five height paths: signed median bars with NMAD
unseen_mesh     the main unseen wall seen from in front: training-view mesh and virtual-view mesh of every training
unseen_gauss    Gaussians (opacity >= 0.5) within 1 m of the main unseen wall, in wall coordinates, coloured by origin
floaters        side view of the Gaussians (opacity >= 0.5), floaters red
scientific_verdict: null."""
import json
import sys

import numpy as np
import open3d as o3d
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

from mt_common import DR, OUT, S0, SITE, boxes, log, setup_fonts, xy_to_uv

plt = setup_fonts()
F = OUT / "figs"
F.mkdir(exist_ok=True)
KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
RUNS = {"LoD2": ["b1_LoD2", "b2_LoD2"], "ALS": ["b1_ALS", "b2_ALS"]}
LAB = {"b1_LoD2": "씨앗 0", "b2_LoD2": "씨앗 1", "b1_ALS": "씨앗 0", "b2_ALS": "씨앗 1", "surface_LoD2": "그대로(표면)", "samepath_LoD2": "그대로(같은 길)",
       "surface_ALS": "그대로(표면)", "samepath_ALS": "그대로(같은 길)"}
CLS_COL = {0: "#2ca02c", 1: "#d62728", 2: "#ff7f0e", 3: "#9e9e9e"}
CLS_KO = {0: "참값 쪽", 1: "틀린 자료 쪽", 2: "둘 다", 3: "둘 다 아님"}
BOX = boxes()["B173nb"]
RNG = np.random.default_rng(0)


def results(prior):
    return RUNS[prior] + [f"surface_{prior}", f"samepath_{prior}"]


def have(r):
    return (OUT / "metrics" / f"{r}_rows.npz").exists()


def frame(ax):
    eu, ev = BOX["eval_u"], BOX["eval_v"]
    ax.plot([eu[0], eu[1], eu[1], eu[0], eu[0]], [ev[0], ev[0], ev[1], ev[1], ev[0]], "k-", lw=0.6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def thin(idx, n):
    return idx if len(idx) <= n else np.sort(RNG.choice(idx, n, replace=False))


def gt():
    return np.load(OUT / "defs/gt_classes.npz")


def fig_spread_map():
    """rows: per prior, (a) the prior-side regions 11 + 13 (+ 12 as a record), (b) image wrong 3; columns: the four results."""
    G = gt()
    X = G["xyz"]
    rows_ = [("LoD2", (11, 13, 12), "사전 정보가 틀린 곳(+ 둘 다 틀린 곳, 기록)", "prior_wrong"), ("LoD2", (3,), "영상이 틀린 곳", "image_wrong"),
             ("ALS", (11, 13, 12), "사전 정보가 틀린 곳(+ 둘 다 틀린 곳, 기록)", "prior_wrong"), ("ALS", (3,), "영상이 틀린 곳", "image_wrong")]
    fig, axs = plt.subplots(4, 4, figsize=(24, 20), constrained_layout=True)
    for i, (p, codes, title, key) in enumerate(rows_):
        rw = np.load(OUT / "defs" / f"rows_{p}.npz")
        for j, r in enumerate(results(p)):
            ax = axs[i, j]
            if not have(r):
                ax.set_axis_off()
                continue
            c = np.load(OUT / "metrics" / f"{r}_rows.npz")["cls"]
            m = thin(np.nonzero(np.isin(rw["code"], codes) & (c >= 0))[0], 400_000)
            uv = xy_to_uv(X[rw["point"][m], :2])
            for k in (3, 0, 2, 1):
                mm = c[m] == k
                ax.scatter(uv[mm, 0], uv[mm, 1], s=0.3 if key == "prior_wrong" else 0.8, c=CLS_COL[k], linewidths=0, rasterized=True)
            frame(ax)
            mj = json.loads((OUT / "metrics" / f"{r}.json").read_text())["spread"][key]["all"]
            ax.set_title(f"{KO[p]} {LAB[r]} — {title}\n번짐 몫 {100 * mj['spread']:.1f} % (참값 쪽 {100 * mj['gt_side']:.1f} %, 점 {mj['points']:,})", fontsize=10)
    fig.legend(handles=[Line2D([], [], marker="s", ls="", color=CLS_COL[k], label=CLS_KO[k], markersize=9) for k in (0, 1, 2, 3)], loc="lower center", ncol=4,
               fontsize=11, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle(f"{SITE} 번짐 네 갈래 (위에서 본 참값 점의 갈래; 제목의 번짐 몫은 그 줄의 정의 영역 = 사전 정보가 틀린 곳 · 영상이 틀린 곳)", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / "spread_map.png", dpi=80, bbox_inches="tight")
    plt.close(fig)


def fig_size_curve():
    xs = [0.6, 1.25, 1.75, 2.5, 3.5, 6.0, 12.0]
    fig, axs = plt.subplots(1, 2, figsize=(15, 5.6), constrained_layout=True)
    for ax, p in zip(axs, ("LoD2", "ALS")):
        thr = 1.0 if p == "LoD2" else 2.0
        for r, st, col in zip(results(p), ("-o", "--s", ":^", ":v"), ("#1f77b4", "#2ca02c", "#7f7f7f", "#bcbd22")):
            if not have(r):
                continue
            cv = json.loads((OUT / "metrics" / f"{r}.json").read_text())["spread"]["size_curve_prior_wrong"]
            y = [np.nan if c["all"]["gt_side"] is None else 100 * c["all"]["gt_side"] for c in cv]
            ax.plot(xs, y, st, color=col, label=f"{LAB[r]}", ms=6)
            if r == RUNS[p][0]:
                for x_, c in zip(xs, cv):
                    ax.annotate(f"{c['all']['points']:,}", (x_, 3), ha="center", fontsize=8, color="#555")
        ax.axvline(1.0, color="k", lw=1, ls="-")
        ax.axvline(thr, color="#d62728", lw=1.2, ls="--")
        ax.axvline(4.0, color="#9467bd", lw=1.2, ls=":")
        ax.text(1.0, 101, " τ", fontsize=9)
        ax.text(thr, 95, f" 충돌 문턱 {thr:g}τ", fontsize=9, color="#d62728")
        ax.text(4.0, 101, " 절단 4τ", fontsize=9, color="#9467bd")
        ax.set_xscale("log")
        ax.set_xticks(xs)
        ax.set_xticklabels(["< 1", "1–1.5", "1.5–2", "2–3", "3–4", "4–8", "8 이상"])
        ax.set_ylim(0, 105)
        ax.set_xlabel("|W − 참값| / τ (구간)")
        ax.set_ylabel("참값 쪽 몫 (%)")
        ax.set_title(f"{KO[p]}: 사전 정보가 틀린 곳의 차이 크기별 참값 쪽 몫 (아래 숫자 = 점 수, 씨앗 0)", fontsize=11)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9, loc="lower right")
    fig.savefig(F / "size_curve.png", dpi=95)
    plt.close(fig)


def plane_segments(V, Fc, c, t, L):
    """the stage-0 figs_stage0.plane_segments: intersection of a mesh with the vertical plane through c along t, |s| <= L."""
    npn = np.array([-t[1], t[0], 0.0])
    d = (V - c) @ npn
    dt = d[Fc]
    cross = (dt.min(1) < 0) & (dt.max(1) > 0)
    F_, d_ = Fc[cross], dt[cross]
    ms, Xs = [], []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        m = (d_[:, a] < 0) != (d_[:, b] < 0)
        w = d_[:, a] / np.where(m, d_[:, a] - d_[:, b], 1.0)
        ms.append(m)
        Xs.append(V[F_[:, a]] + w[:, None] * (V[F_[:, b]] - V[F_[:, a]]))
    ms = np.stack(ms, 1)
    Xs = np.stack(Xs, 1)
    ok = ms.sum(1) == 2
    idx = np.argsort(~ms[ok], axis=1, kind="stable")[:, :2]
    X2 = np.take_along_axis(Xs[ok], idx[:, :, None].repeat(3, 2), 1)
    sv = (X2[..., :2] - c[:2]) @ t[:2]
    seg = np.stack([sv, X2[..., 2]], -1)
    return seg[np.abs(sv).min(1) <= L]


def crop_mesh(V, Fc, c, t, L, w=1.0):
    """triangles with a vertex within w of the section plane and L + w along it (small TSDF triangles)."""
    npn = np.array([-t[1], t[0], 0.0])
    near = (np.abs((V - c) @ npn) <= w) & (np.abs((V[:, :2] - c[:2]) @ t[:2]) <= L + w)
    keep = near[Fc].any(1)
    return Fc[keep]


def fig_size_sections():
    S = json.loads((OUT / "defs/sections.json").read_text())["sections"]
    X = gt()["xyz"].astype(np.float64)
    for p in ("LoD2", "ALS"):
        secs = [(k, v) for k, v in S[p].items()]
        P = np.load(OUT / "defs" / f"prior_{p}.npz")
        meshes = {}
        for r in RUNS[p]:
            m = o3d.io.read_triangle_mesh(str(S0 / "stage0" / r / "post/mesh_tsdf.ply"))
            V, Fc = np.asarray(m.vertices), np.asarray(m.triangles)
            meshes[r] = [(V, crop_mesh(V, Fc, np.asarray(v["centre"]), np.asarray(v["t"]), float(v["L"]) / 2)) if v else None for _, v in secs]
            del m
        fig, axs = plt.subplots(2, 3, figsize=(19, 10), constrained_layout=True)
        for ax, (i, (k, v)) in zip(axs.ravel(), enumerate(secs)):
            if v is None:
                ax.set_axis_off()
                ax.set_title(f"[{k}) τ: 패치 없음")
                continue
            c = np.asarray(v["centre"], np.float64)
            t = np.asarray(v["t"], np.float64)
            L = float(v["L"]) / 2
            npn = np.array([-t[1], t[0], 0.0])
            near = (np.abs((X - c) @ npn) <= 0.25) & (np.abs((X[:, :2] - c[:2]) @ t[:2]) <= L)
            sg = (X[near] - c)[:, :2] @ t[:2]
            ax.scatter(sg, X[near, 2], s=1.5, c="k", label=f"참값 점 (±0.25 m) {int(near.sum()):,}", zorder=3)
            ps = plane_segments(P["V"], P["F"], c, t, L)
            ax.add_collection(LineCollection(ps, colors="#d62728", linewidths=2.2, label=f"사전 정보 ({KO[p]}, 정합 후)", zorder=2))
            for r, col in zip(RUNS[p], ("#1f77b4", "#2ca02c")):
                V, Fc = meshes[r][i]
                ss = plane_segments(V, Fc, c, t, L)
                ax.add_collection(LineCollection(ss, colors=col, linewidths=1.1, label=f"결과 {LAB[r]}", zorder=4))
            ax.set_xlim(-L, L)
            zc, zg = float(c[2]), float(c[2]) + float(v["gt_med"])      # the patch on the prior and its GT height
            ax.set_ylim(min(zc, zg) - 2.5, max(zc, zg) + 2.5)
            lo_b, hi_b = k.split("-")
            ax.set_title(f"구간 [{lo_b}, {hi_b or '∞'}) τ — 패치 |참값 − 사전 정보| = {abs(v['gt_med']):.2f} m ({v['ratio']:.1f} τ)", fontsize=10)
            ax.set_xlabel("단면 방향 거리 (m)")
            ax.set_ylabel("z (m, 지역 좌표)")
            ax.grid(alpha=0.3)
            ax.legend(fontsize=8, loc="best")
        fig.suptitle(f"{SITE} 차이 크기 구간별 대표 단면 — {KO[p]} (구간마다 참값 점이 가장 많은 '사전 정보가 틀린' 패치, 결과를 보기 전에 고름)", fontsize=12, x=0.01, ha="left")
        fig.savefig(F / f"size_sections_{p}.png", dpi=90)
        plt.close(fig)
        log("sections", p)


def fig_height_map():
    G = gt()
    X = G["xyz"]
    fig, axs = plt.subplots(2, 4, figsize=(24, 10.5), constrained_layout=True)
    sm = None
    for i, p in enumerate(("LoD2", "ALS")):
        rw = np.load(OUT / "defs" / f"rows_{p}.npz")
        acc = (rw["code"] == 2) & (rw["kind"] == 1)
        inb = G["in_band"][rw["point"]]
        for j, r in enumerate(results(p)):
            ax = axs[i, j]
            if not have(r):
                ax.set_axis_off()
                continue
            dz = np.load(OUT / "metrics" / f"{r}_rows.npz")["dz"]
            mb = thin(np.nonzero(acc & inb)[0], 300_000)
            mr = thin(np.nonzero(acc & ~inb & np.isfinite(dz))[0], 400_000)
            uvb = xy_to_uv(X[rw["point"][mb], :2])
            ax.scatter(uvb[:, 0], uvb[:, 1], s=0.2, c="#bdbdbd", linewidths=0, rasterized=True)
            uv = xy_to_uv(X[rw["point"][mr], :2])
            sm = ax.scatter(uv[:, 0], uv[:, 1], s=0.25, c=dz[mr], cmap="RdBu_r", vmin=-0.5, vmax=0.5, linewidths=0, rasterized=True)
            frame(ax)
            a = json.loads((OUT / "metrics" / f"{r}.json").read_text())["accuracy"]["roof"]
            ax.set_title(f"{KO[p]} {LAB[r]} — 중앙값 {100 * a['median']:+.1f} cm, NMAD {100 * a['nmad']:.1f} cm", fontsize=10)
    if sm is not None:
        fig.colorbar(sm, ax=axs, shrink=0.6, label="z결과 − z참값 (m)")
    fig.suptitle(f"{SITE} 잰 일치의 지붕 높이 차 (회색 = 뺀 가장자리 띠)", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / "height_map.png", dpi=85, bbox_inches="tight")
    plt.close(fig)


def fig_bias_paths():
    pj = json.loads((OUT / "tables/spread_seed.json").read_text())["paths"]
    fig, axs = plt.subplots(1, 2, figsize=(17, 5.6), constrained_layout=True)
    names = ["1 결과 메시", "2 렌더 점", "3 사전 정보 표면", "4 같은 길 메시", "5 MVS 점"]
    for ax, p in zip(axs, ("LoD2", "ALS")):
        if p not in pj:
            ax.set_axis_off()
            continue
        oc = pj[p]["on_common"]
        xs, ys, es, cols, lbl = [], [], [], [], []
        x = 0
        for k, nm in zip(("1", "2", "3", "4", "5"), names):
            for q, s in enumerate(oc[k]):
                xs.append(x)
                ys.append(100 * s["median"])
                es.append(100 * s["nmad"])
                cols.append({"1": "#1f77b4", "2": "#17becf", "3": "#d62728", "4": "#ff7f0e", "5": "#2ca02c"}[k])
                lbl.append(nm + (f"\n씨앗 {q}" if len(oc[k]) > 1 else ""))
                x += 1
            x += 0.5
        ax.bar(xs, ys, color=cols, yerr=es, capsize=4, alpha=0.85)
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xticks(xs)
        ax.set_xticklabels(lbl, fontsize=8)
        ax.set_ylabel("z길 − z참값 부호 있는 중앙값 (cm), 막대 끝 = NMAD")
        ax.set_title(f"{KO[p]}: 같은 지붕 점 {pj[p]['common_points']:,}개 (잰 일치, 가장자리 띠 밖)", fontsize=11)
        ax.grid(alpha=0.3, axis="y")
    fig.savefig(F / "bias_paths.png", dpi=95)
    plt.close(fig)


def wall_frame():
    un = np.load(OUT / "defs/unseen.npz")
    m = un["surf_ext"] == np.bincount(un["surf_ext"]).argmax()
    c = un["centre"][m]
    n = un["normal"][m][0]
    tvec = np.array([-n[1], n[0], 0.0])
    return un, m, c, n, tvec


def shade_view(sc, O, D, light):
    ans = sc.cast_rays(o3d.core.Tensor(np.concatenate([O, D], 1).astype(np.float32)))
    t = ans["t_hit"].numpy()
    nn = ans["primitive_normals"].numpy()
    ok = np.isfinite(t)
    nn = np.where((nn * D).sum(1, keepdims=True) > 0, -nn, nn)
    lam = np.clip((nn * (light / np.linalg.norm(light))).sum(1), 0, 1) * 0.75 + 0.25
    return np.where(ok, lam, 1.0), ok


def fig_unseen_mesh():
    """the main unseen wall seen along its inward normal from 3 m in front of the LoD2 wall plane; each pixel coloured by where
    the first mesh crossing lies: on the plane (+-0.2 m), in front of it, behind it (within 7 m), none."""
    un, m, c, n, tvec = wall_frame()
    cc = c.mean(0)
    s = (c - cc) @ tvec
    zr = (c[:, 2].min(), c[:, 2].max())
    sw = (s.min() - 6, s.max() + 6)
    res = 0.1
    ss, zz = np.meshgrid(np.arange(sw[0], sw[1], res), np.arange(zr[0] - 4, zr[1] + 6, res)[::-1])
    P = cc[None, :] + ss.reshape(-1, 1) * tvec[None, :] + np.column_stack([np.zeros(ss.size), np.zeros(ss.size), zz.reshape(-1) - cc[2]])
    O = P + 3.0 * n[None, :]
    D = np.tile(-n, (len(O), 1))
    runs = [r for p in ("LoD2", "ALS") for r in RUNS[p] if (OUT / "gpu" / r / "mesh_virtual.ply").exists()]
    if not runs:
        return
    cols = np.array([[1, 1, 1], [0.17, 0.63, 0.17], [1.0, 0.5, 0.05], [0.12, 0.47, 0.71]])
    fig, axs = plt.subplots(2, len(runs), figsize=(5.4 * len(runs), 8.6), constrained_layout=True)
    axs = np.asarray(axs).reshape(2, len(runs))
    lab = un["label_inferred"][m]
    for j, r in enumerate(runs):
        for i, (nm, path) in enumerate((("학습 시점 메시", S0 / "stage0" / r / "post/mesh_tsdf.ply"), ("가상 시점 메시", OUT / "gpu" / r / "mesh_virtual.ply"))):
            mesh = o3d.io.read_triangle_mesh(str(path))
            sc = o3d.t.geometry.RaycastingScene()
            sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
            t = sc.cast_rays(o3d.core.Tensor(np.concatenate([O, D], 1).astype(np.float32)))["t_hit"].numpy()
            k = np.zeros(len(t), int)
            k[np.abs(t - 3.0) <= 0.2] = 1
            k[t < 2.8] = 2
            k[(t > 3.2) & (t <= 10.0)] = 3
            ax = axs[i, j]
            ax.imshow(cols[k].reshape(ss.shape + (3,)), extent=[sw[0], sw[1], zr[0] - 4, zr[1] + 6], interpolation="nearest")
            ax.plot(s[lab == 1], c[lab == 1, 2], ",", color="#d62728", alpha=0.4)
            share = float((k[np.isfinite(t)] == 1).mean()) if np.isfinite(t).any() else 0.0
            ax.set_title(f"{r.split('_')[1]} {LAB[r]} — {nm}", fontsize=10)
            ax.set_xlabel("벽 방향 (m)")
            ax.set_ylabel("z (m)")
            del sc, mesh
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=cols[1], label="LoD2 벽면 ±0.2 m에 면"), Patch(color=cols[2], label="벽면 앞(3 m 안)에 면"),
                        Patch(color=cols[3], label="벽면 뒤(7 m 안)에 면"), Patch(facecolor="white", edgecolor="k", label="면 없음")],
               loc="lower center", ncol=4, fontsize=10, bbox_to_anchor=(0.5, -0.05))
    fig.suptitle("가장 큰 못 본 벽(B173, ext 53): LoD2 벽면 3 m 앞에서 벽 쪽으로 본 첫 메시 면의 자리. 빨강 점 = 지금 지붕 위로 추정한 옛 벽 윗부분 패치 중심", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / "unseen_mesh.png", dpi=85, bbox_inches="tight")
    plt.close(fig)


def fig_unseen_gauss():
    un, m, c, n, tvec = wall_frame()
    cc = c.mean(0)
    s = (c - cc) @ tvec
    runs = [r for p in ("LoD2", "ALS") for r in RUNS[p]]
    fig, axs = plt.subplots(1, len(runs), figsize=(5.4 * len(runs), 5.4), constrained_layout=True)
    lab = un["label_inferred"][m]
    for ax, r in zip(axs, runs):
        d = np.load(S0 / "stage0" / r / "model/dump/iteration_30000/gaussians.npz")
        x = d["xyz"].astype(np.float64)
        v = x - cc
        dn = v @ n
        sv = v @ tvec
        sel = (np.abs(dn) <= 1.0) & (sv >= s.min() - 3) & (sv <= s.max() + 3) & (x[:, 2] >= c[:, 2].min() - 3) & (x[:, 2] <= c[:, 2].max() + 3) & (d["opacity"] >= 0.5)
        for org, col, nm in ((0, "#1f77b4", "관측 출신"), (1, "#d62728", "사전 정보 출신")):
            mm = sel & (d["origin"] == org)
            ax.scatter(sv[mm], x[mm, 2], s=0.4, c=col, linewidths=0, rasterized=True, label=f"{nm} {int(mm.sum()):,}")
        ax.plot(s[lab == 1], c[lab == 1, 2], ",", color="k", alpha=0.3)
        ax.set_title(f"{r.split('_')[1]} {LAB[r]}", fontsize=10)
        ax.set_xlabel("벽 방향 (m)")
        ax.set_ylabel("z (m)")
        ax.legend(fontsize=8, loc="lower left", markerscale=12)
    fig.suptitle("가장 큰 못 본 벽(ext 53)에서 1 m 안의 가우시안(불투명도 0.5 이상), 출신별 색. 검정 = 지금 지붕 위로 추정한 패치 중심", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / "unseen_gauss.png", dpi=90)
    plt.close(fig)


def fig_floaters():
    runs = [r for p in ("LoD2", "ALS") for r in RUNS[p] if (OUT / "gpu" / r / "floater_mask.npy").exists()]
    if not runs:
        return
    fig, axs = plt.subplots(len(runs), 1, figsize=(16, 3.4 * len(runs)), constrained_layout=True)
    axs = np.atleast_1d(axs)
    for ax, r in zip(axs, runs):
        d = np.load(S0 / "stage0" / r / "model/dump/iteration_30000/gaussians.npz")
        fm = np.load(OUT / "gpu" / r / "floater_mask.npy")
        x = d["xyz"].astype(np.float64)
        uv = xy_to_uv(x[:, :2])
        ok = (d["opacity"] >= 0.5) & (uv[:, 0] >= BOX["eval_u"][0]) & (uv[:, 0] <= BOX["eval_u"][1]) & (uv[:, 1] >= BOX["eval_v"][0]) & (uv[:, 1] <= BOX["eval_v"][1])
        bg = thin(np.nonzero(ok & ~fm)[0], 400_000)
        ax.scatter(uv[bg, 0], x[bg, 2], s=0.2, c="#9e9e9e", linewidths=0, rasterized=True)
        ax.scatter(uv[fm, 0], x[fm, 2], s=4, c="#d62728", linewidths=0, label=f"떠 있는 조각 {int(fm.sum()):,}")
        fj = json.loads((OUT / "gpu" / r / "floaters.json").read_text())
        ax.set_title(f"{KO[r.split('_')[1]]} {LAB[r]} — 평가 시점 픽셀 몫 {100 * fj['pixel_share']:.3f} %", fontsize=10)
        ax.set_xlabel("u (m)")
        ax.set_ylabel("z (m)")
        ax.legend(fontsize=9, loc="upper right")
    fig.suptitle(f"{SITE} 옆(u–z)에서 본 가우시안(불투명도 0.5 이상, 평가 범위). 빨강 = 참값 최고 표면보다 3 m 넘게 위", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / "floaters.png", dpi=85)
    plt.close(fig)


FIGS = dict(spread_map=fig_spread_map, size_curve=fig_size_curve, size_sections=fig_size_sections, height_map=fig_height_map, bias_paths=fig_bias_paths,
            unseen_mesh=fig_unseen_mesh, unseen_gauss=fig_unseen_gauss, floaters=fig_floaters)

if __name__ == "__main__":
    for nm in (sys.argv[1:] or list(FIGS)):
        FIGS[nm]()
        log("figure", nm)
