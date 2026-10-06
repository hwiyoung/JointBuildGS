"""PHD-MAIN-METRICS-FIX-v1 figures (jointbuildgs:dev, CPU). Names of 2026-10-06; every figure has a 1-2 sentence reading in
the report.

  python figs_mf.py [name ...]

band_v2          support-agreement roof points of B173nb_b10 coloured by the seed-0 training's reading (gentle: height difference,
                 steep and band: normal distance; +-0.2 m), removed (band) points grey; trial band (v1) next to the new band (v2)
obs_sections     4.5: the five observation-error patches of defs/sections_obs.json (chosen before the training results): GT points, MVS
                 points (box MVS back-projected), the registered LoD2 and ALS surfaces, the four training meshes
(more figures are added by the later steps: overlays are drawn by obs_check.py, height proportionality by height_prop.py)
scientific_verdict: null."""
import json
import sys

import numpy as np

from mf_common import DR, MT, OUT, PREP, S0, Views, boxes, log, read_depth_bin, setup_fonts, xy_to_uv

plt = setup_fonts()
F = OUT / "figs"
F.mkdir(exist_ok=True)
RNG = np.random.default_rng(0)
KO = {"LoD2": "LoD2", "ALS": "항공 LiDAR"}


def thin(idx, n):
    return idx if len(idx) <= n else np.sort(RNG.choice(idx, n, replace=False))


def frame(ax, box):
    eu, ev = box["eval_u"], box["eval_v"]
    ax.plot([eu[0], eu[1], eu[1], eu[0], eu[0]], [ev[0], ev[0], ev[1], ev[1], ev[0]], "k-", lw=0.6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def fig_band_v2():
    G = np.load(MT / "defs/gt_classes.npz")
    X = G["xyz"]
    box = boxes()["B173nb"]
    fig, axs = plt.subplots(2, 2, figsize=(17, 11), constrained_layout=True)
    sm = None
    for i, p in enumerate(("LoD2", "ALS")):
        r1 = np.load(MT / "defs" / f"rows_{p}.npz")
        rv1 = np.load(MT / "metrics" / f"b1_{p}_rows.npz")
        rv2 = np.load(OUT / "metrics" / f"b1_{p}_rows.npz")
        R2 = np.load(OUT / "regions_v2" / f"regions_ext_v2_B173nb_b10_{p}.npz")
        code2 = R2["code_ext_v2"][r1["patch"]]
        for j, (tag, roof, inb, val) in enumerate((
                ("시험 계산(v1) 띠", (r1["code"] == 2) & (r1["kind"] == 1), G["in_band"][r1["point"]], rv1["dz"]),
                ("새 띠(v2), 가파른 면은 법선 거리", (code2 == 2) & (r1["kind"] == 1), rv2["acc_in_band_v2"], np.where(rv2["acc_in_band_v2"], np.nan, rv2["acc_val"])))):
            ax = axs[i, j]
            mb = thin(np.nonzero(roof & inb)[0], 300_000)
            mr = thin(np.nonzero(roof & ~inb & np.isfinite(val))[0], 400_000)
            uvb = xy_to_uv(X[r1["point"][mb], :2])
            ax.scatter(uvb[:, 0], uvb[:, 1], s=0.2, c="#bdbdbd", linewidths=0, rasterized=True)
            uv = xy_to_uv(X[r1["point"][mr], :2])
            sm = ax.scatter(uv[:, 0], uv[:, 1], s=0.25, c=val[mr], cmap="RdBu_r", vmin=-0.2, vmax=0.2, linewidths=0, rasterized=True)
            frame(ax, box)
            share = float(inb[roof].mean()) if roof.any() else 0.0
            ax.set_title(f"{KO[p]} 씨앗 0 — {tag}: 뺀 몫 {100 * share:.1f} %, 남은 점 {int((roof & ~inb).sum()):,}", fontsize=11)
    fig.colorbar(sm, ax=axs, shrink=0.6, label="결과 − 참값 (m; 완만한 면은 높이 차, 가파른 면은 법선 거리)")
    fig.suptitle("B173nb_b10 지지 일치 영역의 지붕 점: 시험 계산의 가장자리 띠(왼쪽)와 새 띠(오른쪽). 회색 = 띠로 뺀 점", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / "band_v2.png", dpi=85, bbox_inches="tight")
    plt.close(fig)


def plane_segments(V, Fc, c, t, L):
    """the stage-0 figs_stage0.plane_segments (intersection with the vertical plane through c along t, |s| <= L)."""
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


def fig_obs_sections(defs="sections_obs", out="obs_sections", title="참값 점이 많은 순, 서로 2 m 넘게, 학습 결과를 보기 전에 고름"):
    import json as _j
    import open3d as o3d
    from matplotlib.collections import LineCollection
    S = _j.loads((OUT / "defs" / f"{defs}.json").read_text())["sections"]
    X = np.load(MT / "defs/gt_classes.npz")["xyz"].astype(np.float64)
    planes = [(np.asarray(s["centre"]), np.asarray(s["t"]), float(s["L"]) / 2) for s in S]
    # MVS points near the planes (box MVS of B173nb_b10)
    V = Views()
    mv = PREP / "mvs/box_B173nb_b10/stereo/depth_maps"
    near_mvs = [[] for _ in planes]
    for f in sorted(mv.glob("*.geometric.bin")):
        n = f.name[: -len(".geometric.bin")]
        d = read_depth_bin(f)
        ok = np.isfinite(d) & (d > 0)
        P = V.C(n)[None, :] + d[ok][:, None].astype(np.float64) * V.rays(n, np.float64)[ok]
        for k, (c, t, L) in enumerate(planes):
            npn = np.array([-t[1], t[0], 0.0])
            m = (np.abs((P - c) @ npn) <= 0.25) & (np.abs((P[:, :2] - c[:2]) @ t) <= L) & (np.abs(P[:, 2] - c[2]) <= 4)
            near_mvs[k].append(P[m])
    near_mvs = [np.concatenate(v) if v else np.zeros((0, 3)) for v in near_mvs]
    priors = {p: np.load(MT / "defs" / f"prior_{p}.npz") for p in ("LoD2", "ALS")}
    runs = ["b1_LoD2", "b2_LoD2", "b1_ALS", "b2_ALS"]
    meshes = {}
    for r in runs:
        m = o3d.io.read_triangle_mesh(str(S0 / "stage0" / r / "post/mesh_tsdf.ply"))
        Vr, Fr = np.asarray(m.vertices), np.asarray(m.triangles)
        segs = []
        for c, t, L in planes:
            npn = np.array([-t[1], t[0], 0.0])
            near = (np.abs((Vr - c) @ npn) <= 1.0) & (np.abs((Vr[:, :2] - c[:2]) @ t) <= L + 1)
            segs.append(plane_segments(Vr, Fr[near[Fr].any(1)], c, t, L))
        meshes[r] = segs
        del m
    cols = {"b1_LoD2": "#1f77b4", "b2_LoD2": "#17becf", "b1_ALS": "#9467bd", "b2_ALS": "#e377c2"}
    lab = {"b1_LoD2": "결과 LoD2 씨앗 0", "b2_LoD2": "결과 LoD2 씨앗 1", "b1_ALS": "결과 항공 LiDAR 씨앗 0", "b2_ALS": "결과 항공 LiDAR 씨앗 1"}
    fig, axs = plt.subplots(len(planes), 1, figsize=(15, 4.6 * len(planes)), constrained_layout=True)
    for k, ((c, t, L), s) in enumerate(zip(planes, S)):
        ax = axs[k]
        npn = np.array([-t[1], t[0], 0.0])
        near = (np.abs((X - c) @ npn) <= 0.25) & (np.abs((X[:, :2] - c[:2]) @ t) <= L) & (np.abs(X[:, 2] - c[2]) <= 4)
        ax.scatter((X[near] - c)[:, :2] @ t, X[near, 2], s=1.2, c="k", label=f"참값 점 {int(near.sum()):,}", zorder=3)
        Mv = near_mvs[k]
        ax.scatter((Mv - c)[:, :2] @ t, Mv[:, 2], s=0.6, c="#ff7f0e", alpha=0.5, label=f"MVS 점(신뢰도 1) {len(Mv):,}", zorder=2)
        for p, col in (("LoD2", "#d62728"), ("ALS", "#2ca02c")):
            ps = plane_segments(priors[p]["V"], priors[p]["F"], c, t, L)
            ax.add_collection(LineCollection(ps, colors=col, linewidths=2.0, label=f"사전 정보 {KO[p]}(정합 후)", zorder=1))
        for r in runs:
            ax.add_collection(LineCollection(meshes[r][k], colors=cols[r], linewidths=0.9, label=lab[r], zorder=4))
        ax.set_xlim(-L, L)
        ax.set_ylim(c[2] - 3.0, c[2] + 3.0)
        ax.set_title(f"단면 {k + 1}: 패치 {s['patch']} (참값 점 {s['gt_points']}, 면 경사 {s['slope_deg']}°, 참값 점 자리 MVS − 참값 {100 * s['d_mvs_minus_gt']:+.0f} cm)", fontsize=10)
        ax.set_xlabel("단면 방향 거리 (m)")
        ax.set_ylabel("z (m)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="upper right", ncol=3, markerscale=6)
    fig.suptitle(f"B173nb_b10 관측 오류 영역의 단면 다섯({title}; ±0.25 m 안의 점)", fontsize=12, x=0.01, ha="left")
    fig.savefig(F / f"{out}.png", dpi=85)
    plt.close(fig)


FIGS = dict(band_v2=fig_band_v2, obs_sections=fig_obs_sections,
            obs_sections_steep=lambda: fig_obs_sections("sections_obs_steep", "obs_sections_steep", "17° 넘는 면만, 같은 규칙; 첫 단면 그림을 본 뒤 기록으로 더함"))

if __name__ == "__main__":
    for nm in (sys.argv[1:] or list(FIGS)):
        FIGS[nm]()
        log("figure", nm)
