"""PHD-STAGE2-R8-FOUR-CASES-v1 summary figure (jointbuildgs:dev, CPU).

  python figure_r8.py <out.png>      # mounts: /artifacts (ro), /repo (ro), /r7 (ro), /p8 (rw), /fonts (ro)

Panels
  (1) registered residuals of the tolerance pool (LoD2 roof, LoD2 wall, airborne LiDAR roof; every 10th sample of the 15
      views) with the tolerance tau and the agency spec
  (2) one training view: the judgment each prior pixel reads (patch: vote of a support patch / propagated judgment of a
      missing patch; no patch: its own mark where c_p = 1, nothing where c_p = 0), LoD2 nominal and airborne LiDAR nominal
  (3)-(6) one place per case of the research intent, a vertical section across the main roof (perpendicular to the
      ridge): prior, MVS and the training result back-projected from one training view (points within 0.15 m of the
      section plane); (3) also the run with the prior depth term off; (6) Gaussian centres and the two TSDF meshes.
      Each panel has an inset of the rendered depth with the section line (6: a virtual view of the mesh step)."""
import json
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from mpl_toolkits.axes_grid1.inset_locator import inset_axes  # noqa: E402

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v2 import rule  # noqa: E402

for fp in ["/fonts/NotoSansCJK-Regular.ttc"]:
    if Path(fp).exists():
        fm.fontManager.addfont(fp); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
ART = Path("/artifacts/JointBuildGS")
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
MAPS = S2 / "inputs/maps"
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
IMGDIR = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images"
P8 = Path("/p8"); R7 = Path("/r7")
CFG = json.loads(Path("/repo/configs/phd/stage2_r8_four_cases_v1/r8.json").read_text())
TOL = json.loads((P8 / "stage1/tolerance.json").read_text())["priors"]
ITS = int(CFG["training"]["iterations"])
H, W = 1157, 1600
VIEW_WALL = "DJI_20241217101313_0009_D"          # panel 2
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
SLAB = 0.15
out_png = sys.argv[1]


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


CAMS, IMGS = {}, {}
for l in (SPARSE / "cameras.txt").read_text().splitlines():
    if l.strip() and not l.startswith("#"):
        t = l.split(); CAMS[int(t[0])] = dict(W=int(t[2]), H=int(t[3]), p=[float(x) for x in t[4:]])
for l in (SPARSE / "images.txt").read_text().splitlines():
    t = l.split()
    if len(t) >= 10 and not l.startswith("#") and t[9].lower().endswith(".jpg"):
        IMGS[Path(t[9]).stem] = dict(R=q2R([float(x) for x in t[1:5]]), t=np.array([float(x) for x in t[5:8]]), cam=int(t[8]))


def rays_train(stem):
    im = IMGS[stem]; cam = CAMS[im["cam"]]; fx, fy, cx, cy = cam["p"]
    sx, sy = W / cam["W"], H / cam["H"]
    u = (np.arange(W) + 0.5) / sx; v = (np.arange(H) + 0.5) / sy        # native pixel coordinates of the training pixel centres
    xn = ((u - cx) / fx)[None, :]; yn = ((v - cy) / fy)[:, None]
    R = im["R"]
    d = np.stack([R[0, k] * xn + R[1, k] * yn + R[2, k] for k in range(3)], -1)
    return d, -R.T @ im["t"]


def rs(a):
    return cv2.resize(a.astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST) if a.shape != (H, W) else a.astype(np.float32)


def load_view(setting, run, stem):
    A = rs(np.load(MAPS / f"conf/raw_depth/{stem}.npy")) > 0.5
    M = rs(np.load(MAPS / f"mvs/raw_depth/{stem}.npy")); P = rs(np.load(MAPS / f"prior_{setting}/raw_depth/{stem}.npy"))
    D = np.load(P8 / "runs" / run / f"model/dump/iteration_{ITS}/{stem}_depth.npy").astype(np.float32)
    prod = P8 / "stage1/products" / setting
    lm = rs(np.load(prod / "locmap" / f"{stem}.npy")).astype(np.int64); mk = rs(np.load(prod / "markmap" / f"{stem}.npy")).astype(np.int64)
    return dict(A=A, M=M, P=P, D=D, lm=lm, mk=mk)


# ---------------------------------------------------------------- section geometry (LoD2 main roof 3396, perpendicular to the ridge)
mesh_n = np.load(R7 / "stage1/meshes/M_N.npz"); mesh_b = np.load(R7 / "stage1/meshes/M_B.npz")
surfs = {r["ext"]: r for r in json.loads((P8 / "stage1/products/M_N/surfaces_poly.json").read_text())["surfaces"]}
n3396 = np.array(surfs[3396]["normal"]); h = n3396[:2] / np.linalg.norm(n3396[:2]); h3 = np.array([h[0], h[1], 0.0])
r3 = np.array([-h[1], h[0], 0.0])                                      # along the ridge (the section plane's normal)
V, F, pot = mesh_n["V"], mesh_n["F"], mesh_n["tri_poly"]
O = V[F[pot == 3396]].reshape(-1, 3).mean(0)
TARGET_POLYS = [e for e, r in surfs.items() if r.get("target")]
tmask_n = np.isin(pot, TARGET_POLYS)
tmask_b = np.isin(mesh_b["tri_poly"], TARGET_POLYS) | (mesh_b["tri_poly"] >= 100000)


def face_plane(face, mesh=None, lift=0.0):
    """(unit normal, point) of a LoD2 face; lift raises the point (the +1 m scene's 3396)."""
    VV, FF, PP = (V, F, pot) if mesh is None else (mesh["V"], mesh["F"], mesh["tri_poly"])
    nrm = np.array(surfs[face]["normal"], float)
    return nrm, VV[FF[PP == face]].reshape(-1, 3).mean(0) + np.array([0, 0, lift])


def height_offset(X, plane):
    """vertical offset of points over a face plane (method 3.3: the height difference at the same horizontal position)."""
    nrm, c = plane
    zp = c[2] - (nrm[0] * (X[..., 0] - c[0]) + nrm[1] * (X[..., 1] - c[1])) / nrm[2]
    return X[..., 2] - zp


def section_t_for_wall():
    """along-ridge position where the front wall 3403 has most missing patches with a propagated conflict (LoD2 nominal)."""
    z = np.load(P8 / "runs/dry_M_N/model/monitor/locations.npz")
    st = np.load(P8 / "stage1/products/M_N/store_poly_c0.25.npz")
    m = (z["surface_ext"] == 3403) & (z["state"] == rule.ST_MISSING) & (z["judgment"] == rule.J_CONFLICT)
    t = (st["loc_center"][m] - O) @ r3
    hist, edges = np.histogram(t, bins=np.arange(t.min() - 0.5, t.max() + 1.0, 0.5))
    k = int(np.argmax(hist))
    return 0.5 * (edges[k] + edges[k + 1]), int(m.sum())


def mesh_section(V_, F_, t0, mask=None):
    """segments (s, z) of the triangles of a mesh cut by the plane (X - O).r3 = t0."""
    T = V_[F_] if mask is None else V_[F_[mask]]
    d = (T - O) @ r3 - t0
    segs = []
    for tri, dd in zip(T, d):
        if (dd > 0).all() or (dd < 0).all():
            continue
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if (dd[a] > 0) != (dd[b] > 0) and dd[a] != dd[b]:
                w = dd[a] / (dd[a] - dd[b]); pts.append(tri[a] + w * (tri[b] - tri[a]))
        if len(pts) == 2:
            segs.append([[(p - O) @ h3, p[2]] for p in pts])
    return np.array(segs)


def view_points(v, stem, src, t0, extra_mask=None):
    """(s, z) of the pixels of one source whose back-projected point lies within SLAB of the plane."""
    d, C = rays_train(stem)
    Z = v[src]
    ok = np.isfinite(Z) & (Z > 0)
    if extra_mask is not None:
        ok &= extra_mask
    X = C[None, None, :] + Z[..., None] * d
    tt = (X - O) @ r3 - t0
    sel = ok & (np.abs(tt) <= SLAB)
    Xs = X[sel]
    return np.stack([(Xs - O) @ h3, Xs[:, 2]], 1), sel, Xs


def plane_line_mask(v, stem, t0):
    d, C = rays_train(stem)
    X = C[None, None, :] + np.where(np.isfinite(v["P"]), v["P"], 0)[..., None] * d
    return np.isfinite(v["P"]) & (np.abs((X - O) @ r3 - t0) <= SLAB)


def best_view(setting, t0, s_rng, z_rng, extra=None):
    """the training view with the most prior pixels in the section slab within the s / z window (extra(v) -> mask)."""
    best = None
    for stem in TRAIN:
        P = rs(np.load(MAPS / f"prior_{setting}/raw_depth/{stem}.npy"))
        d, C = rays_train(stem)
        X = C[None, None, :] + np.where(np.isfinite(P), P, 0)[..., None] * d
        ss = (X - O) @ h3; tt = (X - O) @ r3 - t0
        m = np.isfinite(P) & (np.abs(tt) <= SLAB) & (ss >= s_rng[0]) & (ss <= s_rng[1]) & (X[..., 2] >= z_rng[0]) & (X[..., 2] <= z_rng[1])
        if extra is not None:
            m &= extra(stem)
        k = int(m.sum())
        if best is None or k > best[0]:
            best = (k, stem)
    return best[1], best[0]


def depth_inset(ax, D, line_mask, title, box, loc="upper right"):
    y0, y1, x0, x1 = box
    ins = inset_axes(ax, width="30%", height="30%", loc=loc, borderpad=0.6)
    crop = D[y0:y1, x0:x1].copy(); crop[~np.isfinite(crop) | (crop <= 0)] = np.nan
    ins.imshow(crop, cmap="viridis"); ins.set_xticks([]); ins.set_yticks([])
    lm = line_mask[y0:y1, x0:x1]
    yy, xx = np.nonzero(lm)
    ins.scatter(xx[::7], yy[::7], s=0.4, c="red")
    ins.set_title(title, fontsize=6.5, pad=2)


def bbox(mask, pad=40):
    yy, xx = np.nonzero(mask)
    if len(yy) == 0:
        return 0, H, 0, W
    return max(0, yy.min() - pad), min(H, yy.max() + pad), max(0, xx.min() - pad), min(W, xx.max() + pad)


fig = plt.figure(figsize=(24, 14.5))
gs = fig.add_gridspec(2, 4, height_ratios=[1, 1.15], hspace=0.28, wspace=0.18)

# ---------------------------------------------------------------- (1) residuals
sub = gs[0, 0:2].subgridspec(1, 3, wspace=0.25)
for i, (prior, kind, title, rng) in enumerate((("M", "roof", "LoD2 지붕 (높이 차이)", 0.4), ("M", "wall", "LoD2 벽 (면에 수직인 거리)", 1.0),
                                               ("L", "roof", "항공 LiDAR 지붕 (높이 차이)", 0.4))):
    ax = fig.add_subplot(sub[0, i])
    x = np.load(P8 / "stage1" / f"residuals_{prior}.npz")[kind]
    o = TOL[prior][kind]; tau = o["tau"]; spec = o["spec"]; med = o["stats"]["median_after"]
    ax.hist(x, bins=161, range=(-rng, rng), color="#7a8fa6")
    out_share = float((np.abs(x) > rng).mean())
    for sgn in (-1, 1):
        ax.axvline(med + sgn * tau, color="#c0392b", lw=1.4)
        if spec is not None and spec <= rng:
            ax.axvline(sgn * spec, color="black", ls="--", lw=1.2)
    ax.axvline(med, color="#c0392b", lw=0.8, ls=":")
    note = f"τ = {100 * tau:.1f} cm (중앙값 {100 * med:+.1f} cm 둘레)\n축 밖 {100 * out_share:.1f} %"
    note += f"\n기관 사양 {spec:.2f} m" + (" (축 밖)" if spec is not None and spec > rng else "") if spec is not None else "\n기관 사양 없음"
    ax.text(0.02, 0.97, note, transform=ax.transAxes, va="top", fontsize=8.5, bbox=dict(fc="white", ec="none", alpha=0.8))
    ax.set_title(title, fontsize=10); ax.set_xlabel("잔차 (m), 관측 − 사전 정보"); ax.set_yticks([])
    if i == 0:
        ax.set_ylabel("픽셀 수")
fig.text(0.125, 0.905, "① 잔차 분포와 허용 오차 (빨간 실선 = 중앙값 ± τ, 검은 점선 = ± 기관 사양)", fontsize=12)

# ---------------------------------------------------------------- (2) judgment maps
COLS = {"sa": (0.15, 0.65, 0.25), "sc": (0.85, 0.15, 0.15), "ma": (0.55, 0.85, 0.45), "mc": (0.98, 0.55, 0.10), "mu": (0.95, 0.85, 0.15),
        "inv": (0.1, 0.1, 0.1), "na": (0.20, 0.45, 0.90), "nc": (0.60, 0.20, 0.75), "n0": (0.6, 0.6, 0.6)}
LAB = {"sa": "패치 · 지지 · 일치", "sc": "패치 · 지지 · 충돌", "ma": "패치 · 결측 → 일치", "mc": "패치 · 결측 → 충돌", "mu": "패치 · 결측 → 미판정",
       "na": "패치 없음 · $c_p$ 1 · 일치", "nc": "패치 없음 · $c_p$ 1 · 충돌", "n0": "패치 없음 · $c_p$ 0"}
sub2 = gs[0, 2:4].subgridspec(1, 2, wspace=0.04)
photo = cv2.cvtColor(cv2.resize(cv2.imread(str(next(IMGDIR.glob(VIEW_WALL + ".*")))), (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB) / 255.0
for i, (setting, run, name) in enumerate((("M_N", "M_N", "LoD2 정상"), ("L_N", "L_N", "항공 LiDAR 정상"))):
    ax = fig.add_subplot(sub2[0, i])
    v = load_view(setting, run, VIEW_WALL)
    lz = np.load(P8 / f"runs/dry_{setting}/model/monitor/locations.npz")
    prior = np.isfinite(v["P"]); lm = v["lm"]; located = lm >= 0; lc = np.where(located, lm, 0)
    stt = np.where(located, lz["state"][lc], -1); vt = np.where(located, lz["vote"][lc], -1); jt = np.where(located, lz["judgment"][lc], -1)
    cat = {"sa": located & (stt == rule.ST_SUPPORT) & (vt == rule.V_AGREE), "sc": located & (stt == rule.ST_SUPPORT) & (vt == rule.V_CONFLICT),
           "ma": located & (stt == rule.ST_MISSING) & (jt == rule.J_AGREE), "mc": located & (stt == rule.ST_MISSING) & (jt == rule.J_CONFLICT),
           "mu": located & (stt == rule.ST_MISSING) & np.isin(jt, [rule.J_MIXED, rule.J_INSUFF]), "inv": located & (stt == rule.ST_INVISIBLE),
           "na": ~located & v["A"] & (v["mk"] == rule.MARK_AGREE), "nc": ~located & v["A"] & (v["mk"] == rule.MARK_CONFLICT), "n0": ~located & ~v["A"]}
    img = photo.copy()
    for k, m in cat.items():
        m = m & prior
        img[m] = 0.35 * img[m] + 0.65 * np.array(COLS[k])
    ax.imshow(img); ax.set_xticks([]); ax.set_yticks([])
    shares = {k: (cat[k] & prior).sum() / max(prior.sum(), 1) for k in cat}
    ax.set_title(f"{name}: 패치 있음 {100 * (located & prior).sum() / prior.sum():.0f} %, 없음 {100 * (~located & prior).sum() / prior.sum():.0f} % (사전 정보 픽셀 중)", fontsize=9.5)
fig.legend(handles=[Patch(color=COLS[k], label=LAB[k]) for k in LAB], loc="upper right", bbox_to_anchor=(0.905, 0.555), ncol=4, fontsize=8.5, frameon=False)
fig.text(0.52, 0.905, f"② 대표 시점({VIEW_WALL.split('_')[2]})에서 픽셀이 읽는 판정 — $g_p$ = 0인 곳: 충돌(빨강·주황·보라)", fontsize=12)

# ---------------------------------------------------------------- (3)-(6) sections
t_roof = 0.0
t_wall, n_wall_mc = section_t_for_wall()
tau_roof = TOL["M"]["roof"]["tau"]; tau_wall = TOL["M"]["wall"]["tau"]
roof_lines_n = mesh_section(V, F, t_roof, mask=tmask_n)
roof_lines_b = mesh_section(mesh_b["V"], mesh_b["F"], t_roof, mask=tmask_b)


def plot_prior_band(ax, segs, tau, vertical=True):
    ax.add_collection(LineCollection(segs, colors="#1f4e9b", lw=2.0, label="사전 정보 (LoD2)"))
    for sgn in (-1, 1):
        sh = segs.copy()
        if vertical:
            sh[..., 1] += sgn * tau
        else:
            sh[..., 0] += sgn * tau
        ax.add_collection(LineCollection(sh, colors="#1f4e9b", lw=0.7, linestyles="--"))


def case_panel(ax, setting, run, stem, t0, xlim, ylim, title, band_tau, extra_run=None, highlight=None, vertical_band=True, prior_segs=None,
               inset_loc="upper right", plane=None, nominal_offset_cm=None, legend_loc="lower left"):
    v = load_view(setting, run, stem)
    if plane is None:
        plot_prior_band(ax, prior_segs, band_tau, vertical_band)
    else:   # height offset from the prior face plane: the prior is 0, the tolerance band +-tau
        ax.axhspan(-100 * band_tau, 100 * band_tau, color="#1f4e9b", alpha=0.12, lw=0)
        ax.axhline(0, color="#1f4e9b", lw=2.0, label="사전 정보 (LoD2 면), 띠 = ± τ")
        if nominal_offset_cm is not None:
            ax.axhline(nominal_offset_cm, color="#7f8c8d", lw=1.2, ls="--", label="올리기 전 사전 정보 높이")
    def yv(pts, X):
        return pts[:, 1] if plane is None else 100 * height_offset(X, plane)
    pm, _, Xm = view_points(v, stem, "M", t0, extra_mask=v["A"])
    ax.scatter(pm[:, 0], yv(pm, Xm), s=1.5, c="#e67e22", alpha=0.7, label="MVS (관측 신뢰도 마스크 1)", zorder=3)
    pd_, seld, Xd = view_points(v, stem, "D", t0)
    ax.scatter(pd_[:, 0], yv(pd_, Xd), s=1.5, c="black", alpha=0.7, label="학습 결과", zorder=4)
    if extra_run is not None:
        v2 = load_view(setting, extra_run, stem)
        p2, _, X2 = view_points(v2, stem, "D", t0)
        ax.scatter(p2[:, 0], yv(p2, X2), s=1.5, c="#2ecc71", alpha=0.7, label="사전 정보 깊이 항을 끈 학습", zorder=3.5)
    if highlight is not None:
        ph, _, Xh = view_points(v, stem, "D", t0, extra_mask=highlight(v))
        ax.scatter(ph[:, 0], yv(ph, Xh), s=7, facecolors="none", edgecolors="#c0392b", lw=0.6, label="학습 결과 ($c_p$ 0 · 결측 → 충돌 픽셀)", zorder=5)
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.set_xlabel("단면 위 수평 위치 (m)"); ax.set_ylabel("높이 (m)" if plane is None else "사전 정보 면에서 높이 차이 (cm)")
    ax.set_title(title, fontsize=10.5)
    ax.legend(loc=legend_loc, fontsize=7.5, markerscale=3, framealpha=0.85)
    lm = plane_line_mask(v, stem, t0)
    depth_inset(ax, v["D"], lm, f"렌더링한 깊이 (시점 {stem.split('_')[2]}), 빨강 = 단면", bbox(lm & np.isfinite(v["D"]), 30), inset_loc)


# section extents from the LoD2 roof lines
s_all = roof_lines_n[..., 0].ravel(); z_all = roof_lines_n[..., 1].ravel()
s_eave_front = float(np.max(roof_lines_n[..., 0]))
VIEW_ROOF, n_roof_px = best_view("M_N", t_roof, (s_eave_front - 7.5, s_eave_front + 0.3), (-24.8, -20.2))
ax3 = fig.add_subplot(gs[1, 0])
case_panel(ax3, "M_N", "M_N", VIEW_ROOF, t_roof, (s_eave_front - 7.5, s_eave_front - 0.3), (-25, 25),
           f"③ 관측 있음 · 허용 오차 안 (LoD2 정상, 주지붕)\n띠 = 사전 정보 ± τ ({100 * tau_roof:.1f} cm)", tau_roof, extra_run="M_N_noprior",
           plane=face_plane(3396), inset_loc="upper left", legend_loc="upper center")
ax4 = fig.add_subplot(gs[1, 1])
case_panel(ax4, "M_B", "M_B", VIEW_ROOF, t_roof, (s_eave_front - 7.5, s_eave_front - 0.3), (-125, 25),
           "④ 관측 있음 · 허용 오차 밖 (LoD2 주지붕 +1 m)\n사전 정보를 1 m 올림, 지지 패치는 충돌 ($g_p$ = 0)", tau_roof,
           plane=face_plane(3396, lift=1.0), nominal_offset_cm=-100.0, inset_loc="center left", legend_loc="center right")
wall_lines = mesh_section(V, F, t_wall, mask=np.isin(pot, [3403]))
s_wall = float(np.median(wall_lines[..., 0])) if len(wall_lines) else s_eave_front
VIEW_WALL5, n_wall_px = best_view("M_N", t_wall, (s_wall - 0.9, s_wall + 0.5), (-43.6, -24.3))
ax5 = fig.add_subplot(gs[1, 2])


def hl_wall(v):
    lz = np.load(P8 / "runs/dry_M_N/model/monitor/locations.npz")
    lm = v["lm"]; ok = lm >= 0; lc = np.where(ok, lm, 0)
    return ok & ~v["A"] & (lz["state"][lc] == rule.ST_MISSING) & (lz["judgment"][lc] == rule.J_CONFLICT)


case_panel(ax5, "M_N", "M_N", VIEW_WALL5, t_wall, (s_wall - 0.9, s_wall + 0.5), (-43.6, -24.3),
           f"⑤ 관측 없음 · 영상에 찍힘 (LoD2 정상, 정면 벽)\n결측 → 충돌 패치 ($g_p$ = 0), 파선 = 사전 정보 ± τ ({100 * tau_wall:.1f} cm)", tau_wall,
           highlight=hl_wall, vertical_band=False, prior_segs=wall_lines, inset_loc="center left")
# (6) not in any image: Gaussian centres and meshes over the back roof 3393 (height offset from its plane)
ax6 = fig.add_subplot(gs[1, 3])
pl93 = face_plane(3393)
SLAB6 = 1.5
ax6.axhspan(-100 * tau_roof, 100 * tau_roof, color="#1f4e9b", alpha=0.12, lw=0)
ax6.axhline(0, color="#1f4e9b", lw=2.0, label="사전 정보 (LoD2 뒷지붕 면), 띠 = ± τ")
gz = np.load(P8 / f"runs/M_N/model/dump/iteration_{ITS}/gaussians.npz")
X = gz["xyz"]; tt = (X - O) @ r3 - t_roof
ids = gz["init_id"].astype(np.int64); ext = np.where(ids >= 0, gz["init_surface_ext"][np.maximum(ids, 0)], -1)
on93 = (ext == 3393) & (np.abs(tt) <= SLAB6)
pr = gz["origin"] == 1; op = gz["opacity"]; inv0 = gz["init_category"] == 3
for sel, col, lab in ((on93 & ~inv0 & (op >= 0.5), "#bbbbbb", "그 밖에 이 면에서 출발한 가우시안"),
                      (on93 & inv0 & (op >= 0.5), "#8e44ad", "비가시 패치에서 심은 가우시안 (불투명도 ≥ 0.5)"),
                      (on93 & inv0 & (op < 0.5), "#f39c12", "비가시 패치에서 심은 가우시안 (불투명도 < 0.5)")):
    P_ = X[sel]
    ax6.scatter((P_ - O) @ h3, 100 * height_offset(P_, pl93), s=5, c=col, label=f"{lab} {int(sel.sum()):,}", zorder=3)
c93 = V[F[pot == 3393]].reshape(-1, 3)
s93 = (c93 - O) @ h3
for f_, col, lab in (("mesh_train.ply", "#16a085", "메시 단면: 학습 시점만"), ("mesh_train_virtual.ply", "#c0392b", "메시 단면: 학습 시점 + 더한 시점")):
    fpath = P8 / "mesh/M_N" / f_
    if fpath.exists():
        import open3d as o3d
        mm = o3d.io.read_triangle_mesh(str(fpath))
        Vm = np.asarray(mm.vertices); Fm = np.asarray(mm.triangles)
        cen = Vm[Fm].mean(1)
        keep = (np.abs(((cen - O) @ h3) - 0.5 * (s93.min() + s93.max())) <= 0.5 * (s93.max() - s93.min()) + 1.0) & (np.abs((cen - O) @ r3 - t_roof) <= 1.0)
        segs = mesh_section(Vm, Fm, t_roof, mask=keep)
        if len(segs):
            P3 = O[None, None, :] + segs[..., 0:1] * h3[None, None, :]
            P3[..., 2] = segs[..., 1]
            off = 100 * height_offset(P3, pl93)
            ax6.add_collection(LineCollection(np.stack([segs[..., 0], off], -1), colors=col, lw=1.3, alpha=0.9))
        ax6.plot([], [], color=col, label=lab)
ax6.set_xlim(s93.min() - 0.3, s93.max() + 0.3); ax6.set_ylim(-60, 60)
ax6.set_xlabel("단면 위 수평 위치 (m)"); ax6.set_ylabel("사전 정보 면에서 높이 차이 (cm)")
ax6.set_title("⑥ 영상에 찍히지 않음 (LoD2 정상, 뒷지붕)\n이 면에서 출발한 가우시안 중심(단면 ±1.5 m)과 메시 단면", fontsize=10.5)
ax6.legend(loc="upper left", fontsize=7.2, markerscale=2, framealpha=0.85)
vv = P8 / "mesh/M_N/virtual_view.npz"
if vv.exists():
    z = np.load(vv)
    al = z["alpha"].astype(np.float32) > 0.5
    nm = np.moveaxis(z["normal"].astype(np.float32), 0, -1)
    img = np.ones(al.shape + (3,), np.float32); img[al] = np.clip(0.5 * (nm[al] + 1.0), 0, 1)
    yy, xx = np.nonzero(al)
    if len(yy):
        img = img[yy.min():yy.max() + 1, xx.min():xx.max() + 1]
    ins = inset_axes(ax6, width="32%", height="32%", loc="upper right", borderpad=0.6)
    ins.imshow(img); ins.set_xticks([]); ins.set_yticks([])
    ins.set_title("렌더링한 법선 (더한 시점 하나)", fontsize=6.5, pad=2)
fig.text(0.125, 0.035, "③–⑥ 네 경우의 대표 자리: 주지붕에 수직인 연직 단면(3,500회 학습 결과). ③–⑤는 단면 픽셀이 가장 많은 학습 시점 한 장의 픽셀을 3차원으로 되돌려 단면 ±0.15 m 안의 점만, "
         "③·④·⑥은 사전 정보 면에서의 높이 차이(문서 3.3)로 그렸다. ⑥은 학습 시점이 보지 못하는 면이라 가우시안 중심과 메시를 그렸다.", fontsize=10.5)
fig.savefig(out_png, dpi=110, bbox_inches="tight")
print("saved", out_png, "views", VIEW_ROOF, n_roof_px, VIEW_WALL5, n_wall_px, "wall section t", t_wall, "missing-conflict patches on 3403", n_wall_mc)
