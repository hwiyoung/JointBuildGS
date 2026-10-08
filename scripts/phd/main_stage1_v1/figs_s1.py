"""PHD-MAIN-STAGE1-v1 figures of the results (jointbuildgs:dev, CPU; order 5.1). Methods that exist for a site are drawn; missing ones
are left blank with a note.

  python figs_s1.py discrim <site>      discrimination maps: per prior x method, the thinned GT points of the prior-error and observation-
                                        error regions coloured GT side / wrong side / both / neither (plan view, box u-v)
  python figs_s1.py sections [site]     the sections of configs sections_v1.json (those of one site when given): GT points, MVS points (box
                                        MVS), the registered priors and the results' meshes, points within 0.25 m of the plane
  python figs_s1.py curves              correction-rate curves per prior and method (pooled over the sites read so far), point counts per bin
  python figs_s1.py views               the figure views and the unseen wall face of every site, from camera geometry and the GT only
                                        (written before any stage-1 result) -> /out/defs/fig_views_v1.json
  python figs_s1.py overall <site>      per view (nadir, oblique): evaluation photo; per method the render, rendered depth (common range),
                                        rendered normal and the TSDF mesh ray-cast from the same camera; every panel cropped to the image
                                        rectangle of the post box (the TSDF box of gpu_s1.box_of: its 8 corners projected, + 20 px)
  python figs_s1.py unseen <site>       the unseen wall face unfolded (along the wall x height): its patches by the inferred label, and per
                                        method the virtual-view mesh (option 2) within 0.5 m of the face, 0.2 m cells coloured by the origin of
                                        the nearest Gaussian (opacity >= 0.5, within 0.25 m)
  python figs_s1.py floating <site>     side view (box u x height) of the floating Gaussians (the floater rule of the trial) by origin over
                                        the other Gaussians (opacity >= 0.5) and the top-raster silhouette
scientific_verdict: null."""
import json
import sys
from pathlib import Path

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

from s1_common import DR, GRID_H, GRID_W, OUT, PREP, PRIOR_KO, S0, SITES, Views, boxes, jdump, log, read_depth_bin, setup_fonts, uv_to_xy, xy_to_uv

plt = setup_fonts()
F = OUT / "figs"
METHODS = [("prop_{p}_s0", "본 방법 씨앗 0"), ("imgonly_s0", "영상만"), ("trust_{p}", "늘 믿음"), ("samepath_{p}", "사전 정보 그대로(같은 길)")]
CLS_COL = np.array([[0.17, 0.63, 0.17], [0.84, 0.15, 0.16], [1.0, 0.6, 0.0], [0.6, 0.6, 0.6]])
CLS_KO = ["참값 쪽", "틀린 자료 쪽", "둘 다", "둘 다 아님"]
FIGM = [("prop_LoD2_s0", "본 방법 LoD2"), ("prop_ALS_s0", "본 방법 항공 LiDAR"), ("imgonly_s0", "영상만"), ("trust_ALS", "늘 믿음 항공 LiDAR"),
        ("trust_LoD2", "늘 믿음 LoD2(GeoGS)"), ("prop_ALS1x_s0", "본 방법 항공 LiDAR 1배")]
ORG_COL = {1: (0.84, 0.15, 0.16), 0: (0.12, 0.47, 0.71), -1: (0.35, 0.35, 0.35)}
ORG_KO = {1: "사전 정보 출신", 0: "영상 출신", -1: "0.25 m 안에 가우시안 없음"}


def fig_methods(site):
    return [m for m in FIGM if m[0] != "prop_ALS1x_s0" or site in ("R1rep_b10", "B0_b10")]


def unit_of(res):
    return "ALS" if "ALS" in res else "LoD2"


def in_eval(uv, b):
    return (uv[:, 0] >= b["eval_u"][0]) & (uv[:, 0] <= b["eval_u"][1]) & (uv[:, 1] >= b["eval_v"][0]) & (uv[:, 1] <= b["eval_v"][1])


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


def sections(only=None):
    import open3d as o3d
    from metrics_s1 import result_paths
    S = json.loads((OUT / "defs/sections_v1.json").read_text())["sections"]
    V = Views()
    names = [k for k in S if only is None or S[k]["site"] == only]
    fig, axs = plt.subplots(len(names), 1, figsize=(15, 4.8 * len(names)), constrained_layout=True, squeeze=False)
    axs = axs[:, 0]
    cols = {"prop": "#1f77b4", "imgonly": "#ff7f0e", "trust": "#8c564b", "samepath": "#7f7f7f", "prop_other": "#9467bd"}
    for k, nm in enumerate(names):
        s = S[nm]
        ax = axs[k]
        site, prior = s["site"], s["prior"]
        c, t, L = np.asarray(s["centre"]), np.asarray(s["t"]), float(s["L"]) / 2
        npn = np.array([-t[1], t[0], 0.0])
        zlo, zhi = min(c[2], c[2] + s["gt_med"]) - 3.0, max(c[2], c[2] + s["gt_med"]) + 3.0     # the prior and the GT both inside
        G = np.load(OUT / "defs" / site / "gt_classes.npz")
        X = G["xyz_gt_primary" if (site.startswith("B0") and "xyz_gt_primary" in G.files) else "xyz_gt_points"].astype(np.float64)
        near = (np.abs((X - c) @ npn) <= 0.25) & (np.abs((X[:, :2] - c[:2]) @ t) <= L) & (X[:, 2] >= zlo - 1) & (X[:, 2] <= zhi + 1)
        ax.scatter((X[near] - c)[:, :2] @ t, X[near, 2], s=1.0, c="k", label=f"참값 점 {int(near.sum()):,}", zorder=3)
        mv = PREP / "mvs" / f"box_{site}" / "stereo/depth_maps"
        Mv = []
        for f in sorted(mv.glob("*.geometric.bin")):
            n = f.name[: -len(".geometric.bin")]
            d = read_depth_bin(f)
            ok = np.isfinite(d) & (d > 0)
            P = V.C(n)[None, :] + d[ok][:, None].astype(np.float64) * V.rays(n, np.float64)[ok]
            m = (np.abs((P - c) @ npn) <= 0.25) & (np.abs((P[:, :2] - c[:2]) @ t) <= L) & (P[:, 2] >= zlo - 1) & (P[:, 2] <= zhi + 1)
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
        ax.set_ylim(zlo, zhi)
        ax.set_title(f"{nm} ({site}, {s['why']}; 패치 {s['patch']}, 참값 − {PRIOR_KO[prior]} {100 * s['gt_med']:+.0f} cm)", fontsize=10)
        ax.set_xlabel("단면 방향 거리 (m)")
        ax.set_ylabel("z (m)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="upper right", ncol=4, markerscale=6)
    fig.suptitle("단면(학습 결과를 보기 전에 규칙으로 고른 자리, ±0.25 m 안의 점)", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / (f"sections_{only}.png" if only else "sections_s1.png"), dpi=80)
    plt.close(fig)


def curves(sites=None):
    sites = sites or list(SITES)
    fig, axs = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    for ax, prior in zip(axs, ("LoD2", "ALS")):
        for tmpl, lab in METHODS:
            pts, rates = {}, {}
            for site in sites:
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
        ax.set_title(f"{PRIOR_KO[prior]}: 어긋남 크기별 보정률 ({', '.join(sites) if len(sites) < len(SITES) else '지역을 합침'}, 솎은 점)", fontsize=11)
        ax.legend(fontsize=8)
    fig.savefig(F / ("curves_s1.png" if len(sites) == len(SITES) else f"curves_{'_'.join(sites)}.png"), dpi=85)
    plt.close(fig)


def view_defs():
    """figure views: among the site's test views (split.json), the nadir view (tilt <= 20 deg) and the oblique view (tilt >= 45 deg) whose
    projection of the target - the centre of the evaluation range at the median height of the GT points inside it - lies nearest the image
    centre (in front of the camera and inside the image). Unseen face (sites with defs/<site>/unseen.npz): the LoD2 face (surf_ext) with
    the most unseen wall patches; its centroid, horizontal normal (mean of the patch normals), along-wall direction t = (-n_y, n_x, 0) and
    the s / z ranges of its patches. Camera geometry and GT only; written before any stage-1 result."""
    Vw = Views()
    names = {n.rsplit(".", 1)[0]: n for n in Vw.names}
    bx = boxes()
    out = dict(rule=view_defs.__doc__, written_before_stage1_results=True, sites={}, scientific_verdict=None)
    for site in SITES:
        b = bx[SITES[site]]
        test = json.loads((S0 / "fork_inputs/s61" / site / "split.json").read_text())["test"]
        G = np.load(OUT / "defs" / site / "gt_classes.npz")["xyz_gt_points"].astype(np.float64)
        ine = in_eval(xy_to_uv(G[:, :2]), b)
        cxy = uv_to_xy(np.array([[np.mean(b["eval_u"]), np.mean(b["eval_v"])]]))[0]
        T = np.array([cxy[0], cxy[1], float(np.median(G[ine, 2]))])
        best = {}
        for v in test:
            n = names[v]
            tl = Vw.tilt(n)
            kind = "nadir" if tl <= 20 else ("oblique" if tl >= 45 else None)
            if kind is None:
                continue
            u_, v_, z_ = Vw.project(n, T[None])
            if not (z_[0] > 0 and 0 <= u_[0] < GRID_W and 0 <= v_[0] < GRID_H):
                continue
            dpx = float(np.hypot(u_[0] - GRID_W / 2, v_[0] - GRID_H / 2))
            if kind not in best or dpx < best[kind]["dist_px"]:
                best[kind] = dict(view=v, tilt_deg=round(tl, 2), dist_px=round(dpx, 1))
        ent = dict(target=[round(float(x), 3) for x in T], test_views=len(test), **best)
        uf = OUT / "defs" / site / "unseen.npz"
        if uf.exists():
            un = np.load(uf)
            vals, cnt = np.unique(un["surf_ext"], return_counts=True)
            f = int(vals[cnt.argmax()])
            m = un["surf_ext"] == f
            nrm = un["normal"][m].mean(0)
            nrm[2] = 0.0
            nrm /= np.linalg.norm(nrm)
            c0 = un["centre"][m].mean(0)
            t = np.array([-nrm[1], nrm[0], 0.0])
            s = (un["centre"][m] - c0) @ t
            zc = un["centre"][m, 2]
            ent["unseen_face"] = dict(surf_ext=f, patches=int(m.sum()), of_patches=int(len(m)), centre=[round(float(x), 3) for x in c0],
                                      normal=[round(float(x), 6) for x in nrm], t=[round(float(x), 6) for x in t],
                                      s_range=[round(float(s.min()), 2), round(float(s.max()), 2)], z_range=[round(float(zc.min()), 2), round(float(zc.max()), 2)])
        out["sites"][site] = ent
        log("views", site, ent.get("nadir"), ent.get("oblique"), ent.get("unseen_face", {}).get("surf_ext"))
    jdump(OUT / "defs/fig_views_v1.json", out)


def metric_json(site, res):
    f = OUT / "metrics" / site / f"{res}__{unit_of(res)}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def post_box(site):
    """= gpu_s1.box_of: the box range rectangle + 2 m, z from the 5th percentile of the box GT (s52) - 5 m to its maximum + 5 m."""
    rng = json.loads((DR / "s02_box" / site / "range.json").read_text())
    poly = np.asarray(rng["polygon_local"], np.float64)
    gz = np.load(DR / "s52/box_gt" / site / "gt_points.npz")["xyz"][:, 2].astype(np.float64)
    return np.array([[poly[:, 0].min() - 2.0, poly[:, 1].min() - 2.0, float(np.percentile(gz, 5)) - 5.0],
                     [poly[:, 0].max() + 2.0, poly[:, 1].max() + 2.0, float(gz.max()) + 5.0]])


def crop_of(Vw, n, BOX, margin=20):
    """image rectangle (y0, y1, x0, x1) of the projected box corners; the whole image when a corner is behind the camera."""
    C = np.array([[BOX[i][0], BOX[j][1], BOX[k][2]] for i in (0, 1) for j in (0, 1) for k in (0, 1)])
    u, v, z = Vw.project(n, C)
    if not (z > 0).all():
        return 0, GRID_H, 0, GRID_W
    return (int(max(0, np.floor(v.min()) - margin)), int(min(GRID_H, np.ceil(v.max()) + margin)),
            int(max(0, np.floor(u.min()) - margin)), int(min(GRID_W, np.ceil(u.max()) + margin)))


def blank(ax, text="결과 없음"):
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=11, transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])


def overall(site):
    import cv2
    import open3d as o3d
    from metrics_s1 import result_paths
    D = json.loads((OUT / "defs/fig_views_v1.json").read_text())["sites"][site]
    Vw = Views()
    names = {n.rsplit(".", 1)[0]: n for n in Vw.names}
    ms = fig_methods(site)
    meshes = {}
    for kind in ("nadir", "oblique"):
        if kind not in D:
            continue
        v = D[kind]["view"]
        n = names[v]
        y0, y1, x0, x1 = crop_of(Vw, n, post_box(site))
        photo = cv2.cvtColor(cv2.imread(str(S0 / "fork_inputs/s61" / site / "scene_LoD2/images" / f"{v}.jpg")), cv2.COLOR_BGR2RGB)
        Z = {}
        for res, _ in ms:
            mp = result_paths(site, res).get("mesh")
            f = Path(mp).parent / "eval" / f"{v}.npz" if mp else None
            if f is not None and f.exists():
                Z[res] = np.load(f)
        dd = np.concatenate([z["depth"][y0:y1, x0:x1][z["depth"][y0:y1, x0:x1] > 0] for z in Z.values()]) if Z else np.zeros(0)
        lo, hi = np.percentile(dd, [2, 98]) if len(dd) else (0.0, 1.0)
        Dr = Vw.rays(n).reshape(-1, 3).astype(np.float64)
        Do = Dr / np.linalg.norm(Dr, axis=1, keepdims=True)
        rays = o3d.core.Tensor(np.concatenate([np.tile(Vw.C(n), (len(Do), 1)), Do], 1).astype(np.float32))
        light = -Do.mean(0) + np.array([0, 0, 0.6])
        light /= np.linalg.norm(light)
        shaded, hits = {}, np.zeros(GRID_H * GRID_W, bool)
        for res, _ in ms:
            mp = result_paths(site, res).get("mesh")
            if mp is None or not Path(mp).exists():
                continue
            if res not in meshes:
                mesh = o3d.io.read_triangle_mesh(str(mp))
                sc = o3d.t.geometry.RaycastingScene()
                sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
                meshes[res] = sc
            ans = meshes[res].cast_rays(rays)
            t_ = ans["t_hit"].numpy()
            nr = ans["primitive_normals"].numpy()
            ok = np.isfinite(t_)
            nr = np.where((nr * Do).sum(1, keepdims=True) > 0, -nr, nr)
            shaded[res] = np.where(ok, np.clip(nr @ light, 0, 1) * 0.75 + 0.25, 1.0).reshape(GRID_H, GRID_W)
            hits |= ok
        hy, hx = np.nonzero(hits.reshape(GRID_H, GRID_W))
        my0, my1, mx0, mx1 = ((max(int(np.percentile(hy, 2)) - 10, 0), min(int(np.percentile(hy, 98)) + 10, GRID_H),
                               max(int(np.percentile(hx, 2)) - 10, 0), min(int(np.percentile(hx, 98)) + 10, GRID_W))
                              if len(hy) else (y0, y1, x0, x1))          # 2-98 % of the hit pixels: scattered floaters do not widen it
        fig, axs = plt.subplots(1 + len(ms), 4, figsize=(4 * 3.4, (1 + len(ms)) * 2.55), constrained_layout=True)
        axs[0, 0].imshow(photo[y0:y1, x0:x1])
        axs[0, 0].set_title(f"평가 사진 {v[-9:]} (기울기 {D[kind]['tilt_deg']:.0f}°)", fontsize=9)
        axs[0, 0].set_xticks([])
        axs[0, 0].set_yticks([])
        for ax in axs[0, 1:]:
            ax.set_axis_off()
        im = None
        for i, (res, lab) in enumerate(ms, start=1):
            p = result_paths(site, res)
            if res in Z:
                rgb = cv2.imread(str(Path(p["mesh"]).parent / "eval" / f"{v}_rgb.png"))
                axs[i, 0].imshow(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)[y0:y1, x0:x1])
                d = Z[res]["depth"].astype(np.float32)[y0:y1, x0:x1]
                d[d <= 0] = np.nan
                im = axs[i, 1].imshow(d, cmap="viridis", vmin=lo, vmax=hi)
                axs[i, 2].imshow(np.clip(0.5 * (Z[res]["normal"].astype(np.float32)[y0:y1, x0:x1] + 1), 0, 1))
            else:
                for ax in axs[i, :3]:
                    blank(ax)
            if res in shaded:
                axs[i, 3].imshow(shaded[res][my0:my1, mx0:mx1], cmap="gray", vmin=0, vmax=1)
            else:
                blank(axs[i, 3])
            axs[i, 0].set_ylabel(lab, fontsize=9)
            for ax in axs[i]:
                ax.set_xticks([])
                ax.set_yticks([])
        for j, tt in enumerate(("렌더", "깊이(같은 색 범위)", "법선(세계 좌표, RGB = (n + 1)/2)", "TSDF 메시(같은 카메라, 메시가 맺힌 부분만)")):
            axs[1, j].set_title(tt, fontsize=9)
        if im is not None:
            fig.colorbar(im, ax=axs[1:, 1], fraction=0.03, label="깊이 (m)")
        fig.suptitle(f"{site} 전체 — {'연직' if kind == 'nadir' else '경사'} 평가 시점: 사진, 방법마다 렌더·깊이·법선·메시 (메시 상자가 비치는 부분만 잘라 보임)",
                     fontsize=11, x=0.01, ha="left")
        fig.savefig(F / f"overall_{site}_{kind}.png", dpi=80)
        plt.close(fig)


def unseen_fig(site):
    import open3d as o3d
    from scipy.spatial import cKDTree
    from metrics_s1 import result_paths
    D = json.loads((OUT / "defs/fig_views_v1.json").read_text())["sites"][site].get("unseen_face")
    if D is None:
        log("unseen figure: no unseen face", site)
        return
    un = np.load(OUT / "defs" / site / "unseen.npz")
    m = un["surf_ext"] == D["surf_ext"]
    c0, nrm, t = (np.asarray(D[k], np.float64) for k in ("centre", "normal", "t"))
    s_lo, s_hi = D["s_range"][0] - 1.0, D["s_range"][1] + 1.0
    z_lo, z_hi = D["z_range"][0] - 1.0, D["z_range"][1] + 1.0
    cell = 0.2
    ns, nz = int(np.ceil((s_hi - s_lo) / cell)), int(np.ceil((z_hi - z_lo) / cell))
    ms = fig_methods(site)
    fig, axs = plt.subplots(1 + len(ms), 1, figsize=(15, 2.3 * (1 + len(ms))), constrained_layout=True)
    s, z = (un["centre"][m] - c0) @ t, un["centre"][m, 2]
    li = un["label_inferred"][m]
    for k, lab, col in ((0, "맞음으로 미룸(물려받아야 할 곳)", "#2ca02c"), (1, "틀림으로 미룸(물려받지 않아야 할 곳)", "#d62728"), (2, "모호", "#bbbbbb")):
        mk = li == k
        axs[0].scatter(s[mk], z[mk], s=1.5, c=col, marker="s", linewidths=0, label=f"{lab} {int(mk.sum()):,}", rasterized=True)
    axs[0].set_title(f"못 본 벽 패치(LoD2 면 {D['surf_ext']}, {D['patches']:,} / {D['of_patches']:,}개)의 미룬 판정", fontsize=10)
    axs[0].set_aspect("equal")
    axs[0].legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), markerscale=5, ncol=3)
    for i, (res, lab) in enumerate(ms, start=1):
        ax = axs[i]
        p = result_paths(site, res)
        if not (p.get("virtual") and Path(p["virtual"]).exists()):
            blank(ax)
            ax.set_title(lab, fontsize=10)
            continue
        V = np.asarray(o3d.io.read_triangle_mesh(str(p["virtual"])).vertices)
        sv, zv, dv = (V - c0) @ t, V[:, 2], (V - c0) @ nrm
        k = (np.abs(dv) <= 0.5) & (sv >= s_lo) & (sv < s_hi) & (zv >= z_lo) & (zv < z_hi)
        V, sv, zv = V[k], sv[k], zv[k]
        org = np.full(len(V), -1, np.int8)
        if p.get("dump") is not None and Path(p["dump"]).exists() and len(V):
            dm = np.load(p["dump"])
            X = dm["xyz"].astype(np.float64)
            og = dm["origin"] if "origin" in dm.files else np.zeros(len(X), np.int8)
            sx = (X - c0) @ t
            sel = (dm["opacity"] >= 0.5) & (np.abs((X - c0) @ nrm) <= 1.0) & (sx >= s_lo - 1) & (sx < s_hi + 1) & (X[:, 2] >= z_lo - 1) & (X[:, 2] < z_hi + 1)
            if sel.any():
                dist, idx = cKDTree(X[sel]).query(V, distance_upper_bound=0.25)
                ok = np.isfinite(dist)
                org[ok] = og[sel][idx[ok]]
        ix = np.clip(((sv - s_lo) / cell).astype(np.int64), 0, ns - 1)
        iz = np.clip(((zv - z_lo) / cell).astype(np.int64), 0, nz - 1)
        cnt = np.zeros((3, nz, ns), np.int32)
        for code in (-1, 0, 1):
            mk = org == code
            np.add.at(cnt[code + 1], (iz[mk], ix[mk]), 1)
        img = np.ones((nz, ns, 3))
        has = cnt.sum(0) > 0
        win = cnt.argmax(0) - 1
        for code in (-1, 0, 1):
            img[has & (win == code)] = ORG_COL[code]
        ax.imshow(img, origin="lower", extent=[s_lo, s_hi, z_lo, z_hi], aspect="equal", interpolation="nearest")
        u = metric_json(site, res).get("unseen", {})
        inh, past = u.get("inheritance_rate_inferred"), u.get("past_shape_invisible_inferred")
        ax.set_title(f"{lab} — 가상 시점 메시가 있는 칸 {int(has.sum()) * cell * cell:,.0f} m²; 상속률 {inh if inh is not None else '—'}, "
                     f"못 본 곳의 과거 형상 {past if past is not None else '—'}", fontsize=10)
    for ax in axs:
        ax.set_xlim(s_lo, s_hi)
        ax.set_ylim(z_lo, z_hi)
        ax.set_ylabel("z (m)")
    axs[-1].set_xlabel("벽을 따라 잰 거리 (m)")
    fig.legend(handles=[Line2D([], [], marker="s", ls="", color=ORG_COL[k], label=ORG_KO[k], markersize=9) for k in (1, 0, -1)], loc="lower center",
               ncol=3, fontsize=10, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle(f"{site} 못 본 곳 — 못 본 벽 면을 펼친 모습(벽을 따라 × 높이, 면에서 0.5 m 안, 0.2 m 칸): 가상 시점 메시를 만든 가우시안의 출신", fontsize=11, x=0.01, ha="left")
    fig.savefig(F / f"unseen_{site}.png", dpi=80, bbox_inches="tight")
    plt.close(fig)


def floating_fig(site):
    from metrics_s1 import result_paths
    b = boxes()[SITES[site]]
    tr = np.load(OUT / "defs" / site / "top_raster.npz")
    g, lo, cell = tr["grid"], tr["lo"], float(tr["cell"])
    yy, xx = np.nonzero(np.isfinite(g))
    uvg = xy_to_uv(lo + (np.stack([xx, yy], 1) + 0.5) * cell)
    inn = in_eval(uvg, b)
    ub = np.floor(uvg[inn, 0] / 0.5).astype(np.int64)
    zt = g[yy[inn], xx[inn]]
    order = np.argsort(ub)
    ubu, first = np.unique(ub[order], return_index=True)
    zmax = np.maximum.reduceat(zt[order], first)
    zmin = float(np.nanpercentile(zt, 1))
    ztop = float(np.nanmax(zt))
    ms = fig_methods(site)
    rng = np.random.default_rng(0)
    fig, axs = plt.subplots(len(ms), 1, figsize=(15, 2.6 * len(ms)), constrained_layout=True, squeeze=False)
    for i, (res, lab) in enumerate(ms):
        ax = axs[i, 0]
        p = result_paths(site, res)
        has_dump = p.get("dump") is not None and Path(p["dump"]).exists()
        has_ply = p.get("ply") is not None and Path(p["ply"]).exists()
        if not (p.get("floater_mask") and Path(p["floater_mask"]).exists() and (has_dump or has_ply)):
            blank(ax)
            ax.set_title(lab, fontsize=10)
            continue
        fm = np.load(p["floater_mask"])
        if has_dump:
            dm = np.load(p["dump"])
            X, opac = dm["xyz"].astype(np.float64), dm["opacity"]
            og = dm["origin"] if "origin" in dm.files else np.zeros(len(X), np.int8)
        else:                       # GeoGS: positions and opacities from the PLY, origin not recorded (drawn as image-origin colour)
            from plyfile import PlyData
            v = PlyData.read(str(p["ply"]))["vertex"]
            X = np.stack([v["x"], v["y"], v["z"]], 1).astype(np.float64)
            opac = 1.0 / (1.0 + np.exp(-np.asarray(v["opacity"], np.float64)))
            og = np.zeros(len(X), np.int8)
        uvx = xy_to_uv(X[:, :2])
        ine = in_eval(uvx, b)
        bg = np.nonzero(ine & (opac >= 0.5) & ~fm)[0]
        bg = rng.choice(bg, min(len(bg), 200_000), replace=False) if len(bg) else bg
        ax.scatter(uvx[bg, 0], X[bg, 2], s=0.1, c="0.8", linewidths=0, rasterized=True)
        ax.plot(ubu * 0.5 + 0.25, zmax, "k-", lw=0.6)
        ylim = (zmin - 2.0, ztop + 25.0)
        above = 0
        for code in (0, 1):
            mk = fm & (og == code)
            above += int((mk & (X[:, 2] > ylim[1])).sum())
            if not has_dump and code == 1:
                continue
            ax.scatter(uvx[mk, 0], np.minimum(X[mk, 2], ylim[1] - 0.3), s=3, c=[ORG_COL[code]], linewidths=0,
                       label=f"{ORG_KO[code] if has_dump else '출신 기록 없음(GeoGS)'} {int(mk.sum()):,}")
        fl = metric_json(site, res).get("floating", {})
        ax.set_title(f"{lab} — 부유 {int(fm.sum()):,}개(3~20 m {fl.get('near_3_20m', '—')}, 그중 사전 정보 출신 {fl.get('near_prior', '—')}; 20 m 넘게 "
                     f"{fl.get('above_20m', '—')}), 평가 영상 화소 몫 {fl.get('pixel_share_all', '—')}" + (f"; 위쪽 경계에 붙여 그린 {above}개" if above else ""), fontsize=9)
        ax.set_xlim(*b["eval_u"])
        ax.set_ylim(*ylim)
        ax.set_ylabel("z (m)")
        ax.legend(fontsize=8, loc="upper right", markerscale=3)
    axs[-1, 0].set_xlabel("상자 u 방향 거리 (m)")
    fig.suptitle(f"{site} 부유 가우시안의 옆모습(평가 범위 안; 검은 선 = 위에서 본 최고 높이, 회색 = 나머지 가우시안 불투명도 ≥ 0.5에서 20만 개)", fontsize=11, x=0.01, ha="left")
    fig.savefig(F / f"floating_{site}.png", dpi=80)
    plt.close(fig)


if __name__ == "__main__":
    a = sys.argv[1:]
    {"discrim": lambda: discrim(a[1]), "sections": lambda: sections(a[1] if len(a) > 1 else None), "curves": lambda: curves(a[1:] or None), "views": view_defs, "overall": lambda: overall(a[1]),
     "unseen": lambda: unseen_fig(a[1]), "floating": lambda: floating_fig(a[1])}[a[0]]()
    log("figure", a)
