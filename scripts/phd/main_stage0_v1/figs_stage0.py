"""PHD-MAIN-STAGE0-v1 5.4 figures (jointbuildgs:dev, CPU; Open3D ray casting). Views and section planes = stage0/fig_defs.json
(computed before any training).

  python figs_stage0.py [runs ...]          default: every stage0/<run> with post/mesh_tsdf.ply (b1_LoD2, b1_ALS, b2_LoD2, b2_ALS)

fig54_photo_render      evaluation photo and the render of every run, the four figure views
fig54_depth_normal_b<k> rendered expected depth (common scale per view) and rendered normal of batch k
fig54_mesh              TSDF mesh shaded: top view (orthographic, box rectangle) and the first oblique figure view, every run
fig54_sections_<prior>  the four section planes: prior (registered mesh), results of both seeds (TSDF), GT points within 0.25 m
fig54_training          scalars over the iterations: Gaussians by origin, protected, opacity quantiles and share >= 0.5 (prior)
fig54_quick             quick GT check: roof height difference (median, NMAD) and shares within 0.2 / 0.5 m by split, every run
fig54_quick_map         plan view of the roof GT points coloured by z_result - z_GT, every run
scientific_verdict: null."""
import json
import sys

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import open3d as o3d

from common import DENSE, DR, GRID_H, GRID_W, OUT, PREP, SCFG, Views, log, xy_to_uv

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
SITE = SCFG["stage0"]["site"]
F = OUT / "figs"; F.mkdir(exist_ok=True)
FD = json.loads((OUT / "stage0/fig_defs.json").read_text())
VIEWS = [v["view"] for v in FD["views"]["nadir"] + FD["views"]["oblique"]]
KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}
SEC_KO = {"B173_wing": "B173 날개", "B173_middle": "B173 가운데 톱니 지붕", "neighbour_wall": "이웃 건물 벽", "old_upper_wall": "옛 벽 윗부분(못 본 곳)"}


def runs_present(args):
    if args:
        return args
    return [r for r in ("b1_LoD2", "b1_ALS", "b2_LoD2", "b2_ALS") if (OUT / "stage0" / r / "post/mesh_tsdf.ply").exists()]


def label(r):
    b, p = r.split("_")
    return f"{KO[p]} · 씨앗 {SCFG['stage0']['batches'][b[1]]['seed']}"


def photo(stem):
    names = {n.rsplit(".", 1)[0]: n for n in Views().names}
    img = cv2.imread(str(DENSE / "images" / names[stem]))
    return cv2.cvtColor(cv2.resize(img, (GRID_W, GRID_H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)


def fig_photo_render(runs):
    fig, axs = plt.subplots(len(VIEWS), 1 + len(runs), figsize=(3.3 * (1 + len(runs)), 2.5 * len(VIEWS)), constrained_layout=True)
    for i, v in enumerate(VIEWS):
        axs[i, 0].imshow(photo(v)); axs[i, 0].set_ylabel(v[-9:], fontsize=8)
        for j, r in enumerate(runs):
            p = OUT / "stage0" / r / "post/eval" / f"{v}_rgb.png"
            if p.exists():
                axs[i, j + 1].imshow(cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB))
        for ax in axs[i]:
            ax.set_xticks([]); ax.set_yticks([])
    axs[0, 0].set_title("평가 사진", fontsize=10)
    for j, r in enumerate(runs):
        axs[0, j + 1].set_title(f"렌더 — {label(r)}", fontsize=10)
    fig.suptitle(f"{SITE} 평가 시점 4장(연직 2, 경사 2): 사진과 30,000회 학습 결과의 렌더", fontsize=11, x=0.01, ha="left")
    fig.savefig(F / "fig54_photo_render.png", dpi=90); plt.close(fig)


def fig_depth_normal(runs):
    for b in sorted({r.split("_")[0] for r in runs}):
        rr = [r for r in runs if r.startswith(b)]
        fig, axs = plt.subplots(len(VIEWS), 2 * len(rr), figsize=(3.3 * 2 * len(rr), 2.5 * len(VIEWS)), constrained_layout=True)
        for i, v in enumerate(VIEWS):
            Z = {r: np.load(OUT / "stage0" / r / "post/eval" / f"{v}.npz") for r in rr}
            dd = np.concatenate([z["depth"][z["depth"] > 0] for z in Z.values()])
            lo, hi = np.percentile(dd, [2, 98]) if len(dd) else (0, 1)
            for j, r in enumerate(rr):
                d = Z[r]["depth"].astype(np.float32); d[d <= 0] = np.nan
                im = axs[i, j].imshow(d, cmap="viridis", vmin=lo, vmax=hi)
                n = Z[r]["normal"].astype(np.float32)
                axs[i, len(rr) + j].imshow(np.clip(0.5 * (n + 1), 0, 1))
            fig.colorbar(im, ax=axs[i, len(rr) - 1], fraction=0.04, label="깊이 (m)")
            axs[i, 0].set_ylabel(v[-9:], fontsize=8)
            for ax in axs[i]:
                ax.set_xticks([]); ax.set_yticks([])
        for j, r in enumerate(rr):
            axs[0, j].set_title(f"깊이 — {label(r)}", fontsize=9); axs[0, len(rr) + j].set_title(f"법선 — {label(r)}", fontsize=9)
        fig.suptitle(f"{SITE} 평가 시점의 렌더 깊이(시점마다 같은 색 범위)와 법선(세계 좌표, RGB = (n + 1)/2), 묶음 {b[1]}", fontsize=11, x=0.01, ha="left")
        fig.savefig(F / f"fig54_depth_normal_{b}.png", dpi=90); plt.close(fig)


def scene_of(mesh):
    sc = o3d.t.geometry.RaycastingScene(); sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    return sc


def shade(sc, mesh, O, D, light=np.array([-0.4, -0.5, 0.77])):
    ans = sc.cast_rays(o3d.core.Tensor(np.concatenate([O, D], 1).astype(np.float32)))
    t = ans["t_hit"].numpy(); n = ans["primitive_normals"].numpy()
    ok = np.isfinite(t)
    n = np.where((n * D).sum(1, keepdims=True) > 0, -n, n)
    lam = np.clip((n * (light / np.linalg.norm(light))).sum(1), 0, 1) * 0.75 + 0.25
    return t, ok, lam, n


def fig_mesh(runs):
    rng = json.loads((DR / "s02_box" / SITE / "range.json").read_text()); poly = np.asarray(rng["polygon_local"])
    lo, hi = poly.min(0), poly.max(0); res = 0.15
    xs = np.arange(lo[0], hi[0], res); ys = np.arange(lo[1], hi[1], res)
    X, Y = np.meshgrid(xs, ys[::-1])
    O = np.stack([X.ravel(), Y.ravel(), np.full(X.size, 250.0)], 1); D = np.tile([0, 0, -1.0], (X.size, 1))
    Vw = Views(); names = {n.rsplit(".", 1)[0]: n for n in Vw.names}
    obl = [names[v["view"]] for v in FD["views"]["oblique"]]          # the config names the first; the second is added for a bird's-eye angle
    fig, axs = plt.subplots(1 + len(obl), len(runs), figsize=(4.6 * len(runs), 4.6 * (1 + len(obl))), constrained_layout=True)
    axs = np.asarray(axs).reshape(1 + len(obl), len(runs))
    zall = []
    crops = {}
    for j, r in enumerate(runs):
        mesh = o3d.io.read_triangle_mesh(str(OUT / "stage0" / r / "post/mesh_tsdf.ply"))
        sc = scene_of(mesh)
        t, ok, lam, _ = shade(sc, mesh, O, D)
        z = np.where(ok, 250.0 - t, np.nan).reshape(X.shape); zall.append(z)
        cm = plt.get_cmap("terrain")
        zn = (z - np.nanpercentile(z, 2)) / max(np.nanpercentile(z, 98) - np.nanpercentile(z, 2), 1e-6)
        rgb = cm(np.clip(np.nan_to_num(zn), 0, 1))[..., :3] * lam.reshape(X.shape)[..., None]
        rgb[~ok.reshape(X.shape)] = 1.0
        axs[0, j].imshow(rgb, extent=[xs[0], xs[-1], ys[0], ys[-1]]); axs[0, j].plot(*np.vstack([poly, poly[:1]]).T, "k-", lw=0.6)
        axs[0, j].set_title(f"위에서 — {label(r)}", fontsize=10); axs[0, j].set_xticks([]); axs[0, j].set_yticks([])
        for k, ov in enumerate(obl):
            Dr = Vw.rays(ov).reshape(-1, 3).astype(np.float64); C = Vw.C(ov)
            Do = Dr / np.linalg.norm(Dr, axis=1, keepdims=True); Oo = np.tile(C, (len(Do), 1))
            t2, ok2, lam2, _ = shade(sc, mesh, Oo, Do, light=-(Do.mean(0)) + np.array([0, 0, 0.6]))
            img = np.where(ok2, lam2, 1.0).reshape(GRID_H, GRID_W)
            hit = ok2.reshape(GRID_H, GRID_W)
            if j == 0:      # crop to where the first run's mesh is (same crop for every run of the row)
                ys, xs_ = np.nonzero(hit)
                crops[k] = (max(ys.min() - 20, 0), min(ys.max() + 20, GRID_H), max(xs_.min() - 20, 0), min(xs_.max() + 20, GRID_W)) if len(ys) else (0, GRID_H, 0, GRID_W)
            y0, y1, x0, x1 = crops[k]
            axs[1 + k, j].imshow(img[y0:y1, x0:x1], cmap="gray", vmin=0, vmax=1); axs[1 + k, j].set_title(f"비스듬히({ov[-13:-4]}, 메시 부분만) — {label(r)}", fontsize=9)
            axs[1 + k, j].set_xticks([]); axs[1 + k, j].set_yticks([])
        log("mesh fig", r, len(mesh.triangles))
    fig.suptitle(f"{SITE} TSDF 메시(학습 시점 깊이 융합, 0.05 m 칸):\n위(색 = 높이, 음영 = 법선)와 경사 평가 시점 둘에서 본 모습", fontsize=11, x=0.01, ha="left")
    fig.savefig(F / "fig54_mesh.png", dpi=90); plt.close(fig)


def plane_segments(V, Fc, c, t, L):
    """intersection of a triangle mesh with the vertical plane through c along the horizontal unit t, kept within |s| <= L:
    [M, 2, 2] segments in (s, z). Every triangle is tested (a large polygon's vertices may all lie far from c)."""
    npn = np.array([-t[1], t[0], 0.0])
    d = (V - c) @ npn
    dt = d[Fc]
    cross = (dt.min(1) < 0) & (dt.max(1) > 0)
    F_, d_ = Fc[cross], dt[cross]
    ms, Xs = [], []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        m = (d_[:, a] < 0) != (d_[:, b] < 0)
        w = d_[:, a] / np.where(m, d_[:, a] - d_[:, b], 1.0)
        ms.append(m); Xs.append(V[F_[:, a]] + w[:, None] * (V[F_[:, b]] - V[F_[:, a]]))
    ms = np.stack(ms, 1); Xs = np.stack(Xs, 1)
    ok = ms.sum(1) == 2
    idx = np.argsort(~ms[ok], axis=1, kind="stable")[:, :2]
    X2 = np.take_along_axis(Xs[ok], idx[:, :, None].repeat(3, 2), 1)
    sv = (X2[..., :2] - c[:2]) @ t[:2]
    seg = np.stack([sv, X2[..., 2]], -1)
    return seg[np.abs(sv).min(1) <= L]


def fig_sections(runs):
    from matplotlib.collections import LineCollection
    g = np.load(DR / "s52/box_gt" / SITE / "gt_points.npz")["xyz"].astype(np.float64)
    meshes = {r: o3d.io.read_triangle_mesh(str(OUT / "stage0" / r / "post/mesh_tsdf.ply")) for r in runs}
    MV = {r: (np.asarray(m.vertices), np.asarray(m.triangles)) for r, m in meshes.items()}
    for prior in ("LoD2", "ALS"):
        rr = [r for r in runs if r.endswith(prior)]
        if not rr:
            continue
        sh = np.asarray(json.loads((OUT / "s61/box" / SITE / prior / "summary.json").read_text())["registration"]["shift_applied"])
        m = np.load(DR / "s02_box" / SITE / ("lod2_mesh.npz" if prior == "LoD2" else "als_mesh.npz"))
        PV = m["V"].astype(np.float64) + sh; PF = m["F"][: int(m["n_poly_tris"])] if prior == "LoD2" else m["F"]
        fig, axs = plt.subplots(2, 2, figsize=(15, 9.5), constrained_layout=True)
        for ax, (key, s) in zip(axs.ravel(), FD["sections"].items()):
            c = np.asarray(s["c"], np.float64); t = np.asarray(s["t"], np.float64); L = float(s["L"])
            npn = np.array([-t[1], t[0], 0.0])
            near = (np.abs((g - c) @ npn) <= 0.25) & (np.abs((g[:, :2] - c[:2]) @ t[:2]) <= L)
            sg = (g[near] - c)[:, :2] @ t[:2]
            ax.scatter(sg, g[near, 2], s=2, c="k", label=f"참값 점 (±0.25 m) {int(near.sum()):,}", zorder=3)
            ps = plane_segments(PV, PF, c, t, L)
            ax.add_collection(LineCollection(ps, colors="#d62728", linewidths=2.2, label=f"사전 정보({KO[prior]}, 정합 후)", zorder=2))
            for r, col in zip(rr, ("#1f77b4", "#2ca02c")):
                V_, F_ = MV[r]
                ss = plane_segments(V_, F_, c, t, L)
                ax.add_collection(LineCollection(ss, colors=col, linewidths=1.2, label=f"결과 {label(r)}", zorder=4))
            zz = [g[near, 2]] if near.any() else []
            allz = np.concatenate(zz + [ps[..., 1].ravel()]) if len(ps) else (zz[0] if zz else np.array([0.0, 1.0]))
            ax.set_xlim(-L, L); ax.set_ylim(np.nanmin(allz) - 2, np.nanmax(allz) + 2)
            ax.set_title(f"{SEC_KO[key]}", fontsize=11); ax.set_xlabel("단면 방향 거리 (m)"); ax.set_ylabel("높이 z (m, 지역 좌표)")
            ax.grid(alpha=0.3); ax.legend(fontsize=8, loc="best")
        fig.suptitle(f"{SITE} 대표 자리 단면 — {KO[prior]}: 빨강 = 사전 정보, 파랑·초록 = 두 씨앗의 결과 메시, 검정 = 참값 점", fontsize=11, x=0.01, ha="left")
        fig.savefig(F / f"fig54_sections_{prior}.png", dpi=95); plt.close(fig)
        log("sections", prior)


def fig_training(runs):
    fig, axs = plt.subplots(2, 2, figsize=(15, 8.5), constrained_layout=True)
    cols = {"b1_LoD2": "#1f77b4", "b1_ALS": "#d62728", "b2_LoD2": "#17becf", "b2_ALS": "#ff9896"}
    for r in runs:
        rows = [json.loads(l) for l in (OUT / "stage0" / r / "model/monitor/scalars.jsonl").read_text().splitlines() if l.strip()]
        it = np.array([x["iteration"] for x in rows])
        c = cols.get(r, "k")
        axs[0, 0].plot(it, [x["n_prior"] for x in rows], color=c, label=f"{label(r)} 사전 정보 출신"); axs[0, 0].plot(it, [x["n_image"] for x in rows], color=c, ls="--", label=f"{label(r)} 관측 출신")
        axs[0, 1].plot(it, [x["n_locked"] for x in rows], color=c, label=label(r))
        q = np.array([x["opacity_q_prior"] or [np.nan] * 3 for x in rows])
        axs[1, 0].plot(it, q[:, 1], color=c, label=f"{label(r)} 중앙값"); axs[1, 0].fill_between(it, q[:, 0], q[:, 2], color=c, alpha=0.12)
        axs[1, 1].plot(it, [x.get("opacity_share_ge05_prior") for x in rows], color=c, label=label(r))
    axs[0, 0].set_title("가우시안 수 (실선 사전 정보 출신, 점선 관측 출신)", fontsize=10); axs[0, 1].set_title("보호 대상 수", fontsize=10)
    axs[1, 0].set_title("사전 정보 출신 불투명도: 중앙값(선)과 10~90 % (띠)", fontsize=10); axs[1, 1].set_title("사전 정보 출신 가운데 불투명도 0.5 이상의 몫", fontsize=10)
    axs[1, 0].axhline(0.05, color="k", ls=":", lw=0.8); axs[1, 1].axhline(0.05, color="k", ls=":", lw=0.8)
    for ax in axs.ravel():
        ax.grid(alpha=0.3); ax.set_xlabel("반복"); ax.legend(fontsize=7)
    fig.suptitle(f"{SITE} 학습 중의 장면 (100회마다 기록; 점선 0.05 = 멈춤 신호의 기준)", fontsize=11, x=0.01, ha="left")
    fig.savefig(F / "fig54_training.png", dpi=90); plt.close(fig)


def fig_quick(runs):
    Q = {r: json.loads((OUT / "quick" / f"quick_{r}.json").read_text()) for r in runs if (OUT / "quick" / f"quick_{r}.json").exists()}
    if not Q:
        return
    parts = ["all", "roof", "wall", "changed", "agreement", "agreement_measured", "agreement_unmeasured", "unseen"]
    pko = {"all": "전체", "roof": "지붕", "wall": "벽", "changed": "바뀐 곳\n(B173 날개)", "agreement": "일치 영역", "agreement_measured": "잰 일치",
           "agreement_unmeasured": "못 잰 일치", "unseen": "못 본 곳\n(옛 벽 윗부분)"}
    fig, axs = plt.subplots(1, 3, figsize=(18, 4.8), constrained_layout=True)
    x = np.arange(len(parts)); w = 0.8 / len(Q)
    for i, (r, q) in enumerate(Q.items()):
        med = [q["parts"][p]["roof_dz"]["median"] for p in parts]; nm = [q["parts"][p]["roof_dz"]["nmad"] for p in parts]
        axs[0].bar(x + (i - len(Q) / 2 + 0.5) * w, [np.nan if v is None else v for v in med], w, yerr=[0 if v is None else v for v in nm], label=label(r), capsize=2)
        axs[1].bar(x + (i - len(Q) / 2 + 0.5) * w, [q["parts"][p]["within"]["le_0_2"] or np.nan for p in parts], w, label=label(r))
        axs[2].bar(x + (i - len(Q) / 2 + 0.5) * w, [q["parts"][p]["within"]["le_0_5"] or np.nan for p in parts], w, label=label(r))
    for ax, t in zip(axs, ("지붕 높이 차이 z결과 − z참값: 중앙값(막대)과 NMAD(오차 막대) (m)", "참값 점 가운데 결과 표면 0.2 m 안의 몫", "참값 점 가운데 결과 표면 0.5 m 안의 몫")):
        ax.set_xticks(x); ax.set_xticklabels([pko[p] for p in parts], fontsize=8); ax.set_title(t, fontsize=10); ax.grid(alpha=0.3, axis="y")
    axs[0].axhline(0, color="k", lw=0.6); axs[0].legend(fontsize=8)
    fig.suptitle(f"{SITE} 참값과 간단히 견주기 (점검용, 본 실험의 지표 아님; 일치 영역은 사전 정보마다 자기 것)", fontsize=11, x=0.01, ha="left")
    fig.savefig(F / "fig54_quick.png", dpi=95); plt.close(fig)
    # map of the roof dz
    g = np.load(DR / "s52/box_gt" / SITE / "gt_points.npz")["xyz"].astype(np.float64)
    uv = xy_to_uv(g[:, :2])
    fig, axs = plt.subplots(1, len(Q), figsize=(4.8 * len(Q), 4.6), constrained_layout=True)
    axs = np.atleast_1d(axs)
    for ax, r in zip(axs, Q):
        z = np.load(OUT / "quick" / f"quick_{r}.npz")["dz"]
        m = np.isfinite(z)
        sc_ = ax.scatter(uv[m, 0], uv[m, 1], c=np.clip(z[m], -1.5, 1.5), cmap="RdBu_r", vmin=-1.5, vmax=1.5, s=0.2, rasterized=True)
        ax.set_aspect("equal"); ax.set_title(label(r), fontsize=10)
    fig.colorbar(sc_, ax=axs[-1], label="z결과 − z참값 (m)")
    fig.suptitle(f"{SITE} 지붕 참값 점에서 결과 높이의 차이 (빨강 = 결과가 높음, 파랑 = 낮음)", fontsize=11, x=0.01, ha="left")
    fig.savefig(F / "fig54_quick_map.png", dpi=95); plt.close(fig)


def main():
    runs = runs_present(sys.argv[1:])
    log("runs", runs)
    for fn in (fig_photo_render, fig_depth_normal, fig_mesh, fig_sections, fig_training, fig_quick):
        try:
            fn(runs)
            log("done", fn.__name__)
        except Exception as e:      # one failing figure must not hide the others; the failure is logged
            log("FAILED", fn.__name__, repr(e))


if __name__ == "__main__":
    main()
