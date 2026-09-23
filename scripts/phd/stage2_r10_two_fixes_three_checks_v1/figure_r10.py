"""PHD-STAGE2-R10-TWO-FIXES-THREE-CHECKS-v1 summary figure (jointbuildgs:dev, CPU).

  python figure_r10.py <out.png>      # mounts: /artifacts (ro), /repo (ro), /r7 (ro), /r8 (ro), /p9 (ro), /p10 (rw), /fonts (ro)

Rows (order r10, 5):
  (ga) the opacity reset at 3,000 (LoD2 nominal, the probe's view): the patches the view sees in the state right before the
       reset and those it sees only right after it, on the photo; accumulated opacity of both states; their depth difference;
       changed (patch, view) pairs per training view
  (na) the party-wall cut: top view of the crop's walls with the cut parts; elevation of the target building's wall 3388 with
       the overlaps it was cut by; right after the reset (3,001) the accumulated opacity and |D(3,001) - D(3,000)| of r9 and r10
  (da) the same added view (r8's virtual camera 3): rendered depth and normal of the product layer (whole scene) and the
       mechanism layer (only the aimed Gaussians); section across the back roof 3393: both TSDF meshes and the prior face
  (ra) airborne LiDAR nominal, the view with the most support / agree c_p = 0 pixels: 'result depth - prior' of the vertex and
       the cell method (and the cell method again); a profile along the image row with most of those pixels
  (ma) airborne LiDAR nominal: the case-3 pixels on the photo by propagated judgment; |result - ground truth| at those pixels
       for r8, r8 again, r9, r9 without fix 'da', r10 vertex and cell"""
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
from matplotlib.lines import Line2D  # noqa: E402

sys.path.insert(0, "/repo")
from src.phd.prior_propagation_v4 import faces as FA  # noqa: E402
from src.phd.prior_propagation_v4 import locations as locs  # noqa: E402
from src.phd.prior_propagation_v4 import orientation as ori  # noqa: E402

for fp in ["/fonts/NotoSansCJK-Regular.ttc"]:
    if Path(fp).exists():
        fm.fontManager.addfont(fp); matplotlib.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
matplotlib.rcParams["axes.unicode_minus"] = False
ART = Path("/artifacts/JointBuildGS")
S2 = ART / "phase-payloads/phd/stage2_conf_guided_gs_v1/PHD-STAGE2-CONF-GUIDED-GS-v1"
MAPS = S2 / "inputs/maps"
IMGDIR = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images"
S1 = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1"
P10 = Path("/p10"); P9 = Path("/p9"); R8 = Path("/r8"); R7 = Path("/r7")
H, W = 1157, 1600
TRAIN = json.loads((S2 / "runs/P_M_N/model/monitor/meta.json").read_text())["train_views"]
out_png = sys.argv[1]
PJ = json.loads((S1 / "inputs/lod2_polygons.json").read_text())
RECT = np.array(PJ["als_crop_local_xy"], float)


def photo(stem):
    return cv2.cvtColor(cv2.resize(cv2.imread(str(next(IMGDIR.glob(stem + ".*")))), (W, H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB) / 255.0


def bbox(mask, pad=40):
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return (0, W, 0, H)
    return (max(xs.min() - pad, 0), min(xs.max() + pad, W), max(ys.min() - pad, 0), min(ys.max() + pad, H))


def show(ax, img, title, box=None, **kw):
    if box is not None:
        x0, x1, y0, y1 = box
        img = img[y0:y1, x0:x1]
    im = ax.imshow(img, **kw); ax.set_xticks([]); ax.set_yticks([]); ax.set_title(title, fontsize=9)
    return im


def normal_rgb(n):
    n = np.asarray(n, np.float32)
    if n.shape[0] == 3:
        n = n.transpose(1, 2, 0)
    return np.clip(0.5 * (n + 1.0), 0, 1)


fig = plt.figure(figsize=(26, 30))
gs = fig.add_gridspec(5, 6, hspace=0.32, wspace=0.12)
row_title = ["(가) 3,000회: 다시 읽기를 초기화 직전과 직후에 했을 때 (LoD2 정상)",
             "(나) 맞댄 벽을 잘라 낸 자리와 초기화 직후 (LoD2 정상)",
             "(다) 같은 더한 시점(r8의 더한 카메라 3)에서 결과물 층과 기제 층 (LoD2 정상)",
             "(라) 항공 LiDAR 정상: 꼭짓점 방식과 칸 방식의 '결과 깊이 − 사전 정보'",
             "(마) 항공 LiDAR 정상: 경우 3 픽셀의 자리와 참값 대비"]
for r, t in enumerate(row_title):
    fig.text(0.02, 0.892 - r * 0.1595, t, fontsize=14, weight="bold")

# ================================================================== (ga)
pz = P10 / "runs/probe_M_N/model/monitor/reset_probe.npz"
if pz.exists():
    z = np.load(pz)
    view = str(z["3000_view"])
    uv = z["3000_cell_uv"]; pre = z["3000_pre_cells_seen"]; post = z["3000_post_cells_seen"]
    ins = (uv[:, 2] > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < W) & (uv[:, 1] >= 0) & (uv[:, 1] < H)
    img = photo(view)
    fid = cv2.resize(np.load(MAPS / f"faceid/{view}.npy").astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
    faces_j = json.loads((MAPS / "faces.json").read_text())
    tmask = np.isin(fid, faces_j["roof"] + faces_j["wall"])
    box = bbox(tmask, 120)
    ax = fig.add_subplot(gs[0, 0:2])
    show(ax, img, f"{view[-9:-2]}: 직전 상태에서 '본다' (초록) · 직후 상태에서만 '본다' (빨강)", box)
    x0, x1, y0, y1 = box
    inb = ins & (uv[:, 0] >= x0) & (uv[:, 0] < x1) & (uv[:, 1] >= y0) & (uv[:, 1] < y1)
    a = inb & pre; b = inb & post & ~pre
    ax.scatter(uv[a, 0] - x0, uv[a, 1] - y0, s=0.3, c="#1a9850", alpha=0.6, linewidths=0)
    ax.scatter(uv[b, 0] - x0, uv[b, 1] - y0, s=0.6, c="#d73027", alpha=0.9, linewidths=0)
    ax.set_xlim(0, x1 - x0); ax.set_ylim(y1 - y0, 0)
    ax.text(0.01, 0.01, f"초록 {int(a.sum()):,} · 빨강 {int(b.sum()):,} · 직후에만 가려짐 {int((inb & pre & ~post).sum()):,}", transform=ax.transAxes,
            fontsize=9, color="w", bbox=dict(fc="k", alpha=0.6))
    for j, (tag, nm) in enumerate((("pre", "직전"), ("post", "직후"))):
        ax = fig.add_subplot(gs[0, 2 + j])
        im = show(ax, z[f"3000_{tag}_alpha"].astype(np.float32), f"누적 불투명도 ({nm})", box, cmap="gray", vmin=0, vmax=1)
    Dpre = z["3000_pre_depth"]; Dpost = z["3000_post_depth"]
    ax = fig.add_subplot(gs[0, 4])
    dd = np.where((Dpre > 0) & (Dpost > 0), Dpost - Dpre, np.nan)
    im = show(ax, dd, "깊이: 직후 − 직전 (m)", box, cmap="RdBu_r", vmin=-20, vmax=20)
    fig.colorbar(im, ax=ax, fraction=0.04)
    gj = json.loads((P10 / "runs/probe_M_N/model/monitor/reset_probe.json").read_text())["3000"]
    ax = fig.add_subplot(gs[0, 5])
    names = list(gj["per_view"]); ch = [gj["per_view"][n_]["cells_changed"] for n_ in names]
    sp = [gj["per_view"][n_]["cells_seen_pre"] for n_ in names]
    ax.barh(range(len(names)), sp, color="#bbbbbb", label="직전에 본 (패치, 시점)")
    ax.barh(range(len(names)), ch, color="#d73027", label="판단이 바뀐 쌍")
    ax.set_yticks(range(len(names))); ax.set_yticklabels([n_[-9:-2] for n_ in names], fontsize=7); ax.legend(fontsize=7, loc="lower right")
    ax.set_title(f"시점별 (패치, 시점) 쌍: 바뀜 {gj['cell_view_pairs_changed']:,} / {gj['cell_view_pairs']:,}", fontsize=9)

# ================================================================== (na)
m9 = np.load(P9 / "stage1/meshes/M_N.npz"); m10 = np.load(P10 / "stage1/meshes/M_N.npz")
cuts = json.loads((P10 / "stage1/meshes/cuts_M_N.json").read_text())
ax = fig.add_subplot(gs[1, 0])
V9, F9 = m9["V"], m9["F"]
wall9 = m9["tri_type"] == "WallSurface"
T = V9[F9[wall9]]
inrect = ((T[..., 0] >= RECT[0, 0] - 5) & (T[..., 0] <= RECT[1, 0] + 5) & (T[..., 1] >= RECT[0, 1] - 5) & (T[..., 1] <= RECT[1, 1] + 5)).all(1)
segs = []
for t in T[inrect]:
    xy = t[:, :2]; d = np.linalg.norm(xy[:, None] - xy[None], axis=2); i, j = np.unravel_index(np.argmax(d), d.shape)
    segs.append([xy[i], xy[j]])
ax.add_collection(LineCollection(segs, colors="#999999", linewidths=0.6))
tgt = PJ["target_building"]
tsel = (m9["tri_building"] == tgt) & (m9["tri_type"] == "RoofSurface")
for t in V9[F9[tsel]]:
    ax.fill(t[:, 0], t[:, 1], color="#fdd49e", lw=0)
from shapely import wkt  # noqa: E402
cut_segs = []
for c in cuts["pairs"]:
    o, e1, e2, n_c = [np.array(x) for x in c["frame"]]
    reg = wkt.loads(c["region_wkt"])
    for gg in getattr(reg, "geoms", [reg]):
        if gg.geom_type != "Polygon":
            continue
        uvp = np.asarray(gg.exterior.coords)
        X = o + uvp[:, :1] * e1 + uvp[:, 1:2] * e2
        if ((X[:, 0] >= RECT[0, 0] - 5) & (X[:, 0] <= RECT[1, 0] + 5) & (X[:, 1] >= RECT[0, 1] - 5) & (X[:, 1] <= RECT[1, 1] + 5)).any():
            d = np.linalg.norm(X[:, None, :2] - X[None, :, :2], axis=2); i, j = np.unravel_index(np.argmax(d), d.shape)
            cut_segs.append([X[i, :2], X[j, :2]])
ax.add_collection(LineCollection(cut_segs, colors="#d73027", linewidths=2.0))
ax.plot([RECT[0, 0], RECT[1, 0], RECT[1, 0], RECT[0, 0], RECT[0, 0]], [RECT[0, 1], RECT[0, 1], RECT[1, 1], RECT[1, 1], RECT[0, 1]], "k--", lw=0.8)
ax.set_xlim(RECT[0, 0] - 3, RECT[1, 0] + 3); ax.set_ylim(RECT[0, 1] - 3, RECT[1, 1] + 3); ax.set_aspect("equal")
ax.set_title("위에서 본 벽(회색), 잘라 낸 겹침(빨강),\n대상 건물 지붕(주황), 크롭(점선)", fontsize=8)
ax.tick_params(labelsize=7)
# elevation of the target building's wall 3388 in the frame of its largest overlap
ax = fig.add_subplot(gs[1, 1])
pairs = [c for c in cuts["pairs"] if 3388 in (c["a"], c["b"])]
big = max(pairs, key=lambda c: c["area_m2"])
o, e1, e2, n_c = [np.array(x) for x in big["frame"]]
fr = (o, e1, e2, n_c)
for t in V9[F9[m9["tri_poly"] == 3388]]:
    uv2 = FA.to_plane(t, fr); ax.plot(np.r_[uv2[:, 0], uv2[0, 0]], np.r_[uv2[:, 1], uv2[0, 1]], color="#4575b4", lw=1.2)
for c in pairs:
    other = c["b"] if c["a"] == 3388 else c["a"]
    for t in V9[F9[m9["tri_poly"] == other]]:
        uv2 = FA.to_plane(t, fr); ax.plot(np.r_[uv2[:, 0], uv2[0, 0]], np.r_[uv2[:, 1], uv2[0, 1]], color="#636363", lw=0.6, ls="--")
    cf = [np.array(x) for x in c["frame"]]
    reg = wkt.loads(c["region_wkt"])
    for gg in getattr(reg, "geoms", [reg]):
        if gg.geom_type == "Polygon":
            uvp = np.asarray(gg.exterior.coords); X = cf[0] + uvp[:, :1] * cf[1] + uvp[:, 1:2] * cf[2]
            uv2 = FA.to_plane(X, fr); ax.fill(uv2[:, 0], uv2[:, 1], color="#d73027", alpha=0.45, lw=0)
            mid = uv2.mean(0); ax.text(mid[0], mid[1], f"{other}", fontsize=7, ha="center")
for t in m10["V"][m10["F"][m10["tri_poly"] == 3388]]:
    uv2 = FA.to_plane(t, fr); ax.fill(uv2[:, 0], uv2[:, 1], color="#4575b4", alpha=0.8, lw=0)
ax.set_aspect("equal"); ax.tick_params(labelsize=7)
ax.set_title("대상 건물 벽 3388 정면도 (m): 파랑 선 = r9 벽,\n빨강 = 이웃 벽(점선, 번호)과 겹쳐 잘라 낸 곳, 파랑 칠 = r10에 남은 부분", fontsize=7)
v0 = "DJI_20241217101359_0032_D"
fid = cv2.resize(np.load(MAPS / f"faceid/{v0}.npy").astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
faces_j = json.loads((MAPS / "faces.json").read_text())
box0 = bbox(np.isin(fid, faces_j["roof"] + faces_j["wall"]), 80)
for j, (tag, root) in enumerate((("r9", P9), ("r10", P10))):
    d = root / "runs/M_N/model/dump"
    if not (d / "iteration_3001").exists():
        continue
    al = np.load(d / "iteration_3001" / f"{v0}_alpha.npy").astype(np.float32)
    ax = fig.add_subplot(gs[1, 2 + j]); show(ax, al, f"{tag} 3,001회 누적 불투명도", box0, cmap="gray", vmin=0, vmax=1)
    D0 = np.load(d / "iteration_3000" / f"{v0}_depth.npy"); D1 = np.load(d / "iteration_3001" / f"{v0}_depth.npy")
    ax = fig.add_subplot(gs[1, 4 + j]); im = show(ax, np.where((D0 > 0) & (D1 > 0), np.abs(D1 - D0), np.nan), f"{tag} |D(3,001) − D(3,000)| (m)", box0, cmap="magma", vmin=0, vmax=25)
    if j == 1:
        fig.colorbar(im, ax=ax, fraction=0.04)

# ================================================================== (da)
fv = P10 / "mesh/M_N/figure_views.npz"
if fv.exists():
    z = np.load(fv)
    k = 3
    Am = z[f"cam{k}_mechanism_alpha"].astype(np.float32) > 0.05
    Dm = z[f"cam{k}_mechanism_depth"][Am]
    lo_, hi_ = (np.percentile(Dm, 2), np.percentile(Dm, 98)) if Am.any() else (None, None)
    ys_, xs_ = np.nonzero(Am)
    hh, ww = Am.shape
    bx = (max(xs_.min() - 60, 0), min(xs_.max() + 60, ww), max(ys_.min() - 60, 0), min(ys_.max() + 60, hh)) if Am.any() else None
    for j, (tag, nm) in enumerate((("product", "결과물 층 (장면 전체)"), ("mechanism", "기제 층 (겨냥한 가우시안만)"))):
        D = z[f"cam{k}_{tag}_depth"]; A_ = z[f"cam{k}_{tag}_alpha"].astype(np.float32)
        ax = fig.add_subplot(gs[2, 2 * j]); im = show(ax, np.where(A_ > 0.05, D, np.nan), f"{nm}: 깊이 (m)", bx, cmap="viridis", vmin=lo_, vmax=hi_)
        if j == 1:
            fig.colorbar(im, ax=ax, fraction=0.04)
        ax = fig.add_subplot(gs[2, 2 * j + 1]); nr = normal_rgb(z[f"cam{k}_{tag}_normal"].astype(np.float32)); nr[A_ < 0.05] = 1.0
        show(ax, nr, f"{nm}: 법선", bx)
    # section across the back roof 3393 (cut along the slope at the face centroid), both meshes and the prior face
    import open3d as o3d
    st = locs.load_store(P10 / "stage1/products/M_N/store_poly_c0.25.npz")
    s_idx = int(np.nonzero(st["surf_ext"] == 3393)[0][0]); mm_ = st["loc_surface"] == s_idx
    c = np.median(st["loc_center"][mm_], 0)
    tab = {r["ext"]: r for r in json.loads((P10 / "stage1/products/M_N/surfaces_poly.json").read_text())["surfaces"]}
    n = np.array(tab[3393]["normal_outward"]); e1, e2 = ori.tangent_frame(n[None]); e1, e2 = e1[0], e2[0]
    ax = fig.add_subplot(gs[2, 4:6])
    for name, col in (("mesh_train_virtual", "#4575b4"), ("mesh_mechanism", "#f46d43")):
        mm = o3d.io.read_triangle_mesh(str(P10 / "mesh/M_N" / f"{name}.ply")); Vm = np.asarray(mm.vertices); Fm = np.asarray(mm.triangles)
        Tm = Vm[Fm]; dd = (Tm - c) @ e1
        keep = ~((dd > 0).all(1) | (dd < 0).all(1))
        sg = []
        for tri, d_ in zip(Tm[keep], dd[keep]):
            pts = []
            for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                if (d_[a_] > 0) != (d_[b_] > 0) and d_[a_] != d_[b_]:
                    t_ = d_[a_] / (d_[a_] - d_[b_]); pts.append(tri[a_] + t_ * (tri[b_] - tri[a_]))
            if len(pts) == 2:
                sg.append(pts)
        sg = np.array(sg)
        if len(sg):
            sx = (sg - c) @ e2
            sy = sg[..., 2] - (c[2] - (n[0] * (sg[..., 0] - c[0]) + n[1] * (sg[..., 1] - c[1])) / n[2])
            k_ = (np.abs(sy).max(1) <= 1.5) & (np.abs(sx).max(1) <= 8)
            ax.add_collection(LineCollection(np.stack([sx[k_], sy[k_]], -1), colors=col, linewidths=1.0))
    ax.axhline(0, color="k", lw=1)
    ax.set_xlim(-8, 8); ax.set_ylim(-1.5, 1.5); ax.tick_params(labelsize=7)
    ax.set_xlabel("경사 방향 (m)", fontsize=8); ax.set_ylabel("사전 정보 면 위 높이 (m)", fontsize=8)
    ax.legend(handles=[Line2D([], [], color="#4575b4", label="결과물 층 TSDF"), Line2D([], [], color="#f46d43", label="기제 층 TSDF"),
                       Line2D([], [], color="k", label="사전 정보 면 (뒷지붕 3393)")], fontsize=7, loc="upper right")
    ax.set_title("뒷지붕 3393의 경사 방향 단면 (면 중심을 지나는 연직면)", fontsize=9)

# ================================================================== (ra)
rz = P10 / "cases/ra_maps.npz"
if rz.exists():
    z = np.load(rz)
    view = str(z["view"])
    rc = z["L_N_vertex_x_support_c0_agree_rc"]
    msk = np.zeros((H, W), bool); msk[rc[:, 0], rc[:, 1]] = True
    box = bbox(msk, 60)
    for j, (run, nm) in enumerate((("L_N_vertex", "꼭짓점"), ("L_N_cell", "칸"), ("L_N_cell_rep", "칸 (다시)"))):
        dP = z[f"{run}_dP"]; tau = z[f"{run}_tau"]
        ax = fig.add_subplot(gs[3, j])
        im = show(ax, np.where(np.isfinite(dP), 100 * dP, np.nan), f"{nm}: 결과 − 사전 정보 (cm), {view[-9:-2]}", box, cmap="RdBu_r", vmin=-15, vmax=15)
        if j == 2:
            fig.colorbar(im, ax=ax, fraction=0.04)
    rows_, cnt = np.unique(rc[:, 0], return_counts=True); row = int(rows_[np.argmax(cnt)])
    ax = fig.add_subplot(gs[3, 3:6])
    xs = np.arange(W)
    on = msk[row]
    for run, col, nm in (("L_N_vertex", "#4575b4", "꼭짓점"), ("L_N_cell", "#d73027", "칸"), ("L_N_cell_rep", "#fdae61", "칸 (다시)")):
        dP = z[f"{run}_dP"][row]
        ax.plot(xs, 100 * dP, color=col, lw=0.6, alpha=0.5)
        ax.plot(xs[on], 100 * dP[on], ".", color=col, ms=3, label=f"{nm} (지지·일치 cₚ 0 픽셀)")
    t_ = 100 * z["L_N_vertex_tau"][row]
    ax.fill_between(xs, -t_, t_, color="#cccccc", alpha=0.5, lw=0, label="± τ")
    x0, x1 = box[0], box[1]
    ax.set_xlim(x0, x1); ax.set_ylim(-20, 20); ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel(f"픽셀 열 (행 {row})", fontsize=8); ax.set_ylabel("결과 − 사전 정보 (cm)", fontsize=8); ax.legend(fontsize=7, ncol=2)
    ax.set_title("한 행을 따라 본 '결과 − 사전 정보' (점 = 지지·일치 패치의 cₚ 0 픽셀)", fontsize=9)

# ================================================================== (ma)
mz = P10 / "cases/ma_maps.npz"
if mz.exists():
    z = np.load(mz)
    view = str(z["view"])
    img = photo(view)
    key0 = "r9_L_N"
    cols = {"c3_agree": "#1a9850", "c3_conflict": "#d73027", "c3_undetermined": "#4575b4"}
    allm = np.zeros((H, W), bool)
    for k in cols:
        rc = z[f"{key0}_{k}_rc"]; allm[rc[:, 0], rc[:, 1]] = True
    box = bbox(allm, 30)
    ax = fig.add_subplot(gs[4, 0:2]); show(ax, img, f"{view[-9:-2]}: 경우 3 픽셀 (초록 일치 · 빨강 충돌 · 파랑 미판정)", box)
    for k, col in cols.items():
        rc = z[f"{key0}_{k}_rc"]
        ax.scatter(rc[:, 1] - box[0], rc[:, 0] - box[2], s=3.0, c=col, linewidths=0)
    tags = [t for t in ("r8_L_N", "r9_r8rep_L_N", "r9_L_N", "r9_L_N_noorient", "r10_L_N_vertex", "r10_L_N_cell") if f"{t}_dG" in z.files]
    lab = {"r8_L_N": "r8", "r9_r8rep_L_N": "r8 다시", "r9_L_N": "r9", "r9_L_N_noorient": "r9 다 끔", "r10_L_N_vertex": "r10 꼭짓점", "r10_L_N_cell": "r10 칸"}
    for j, (k, nm) in enumerate((("c3_agree", "일치"), ("c3_conflict", "충돌"), ("c3_undetermined", "미판정"))):
        ax = fig.add_subplot(gs[4, 2 + j])
        data = []
        for t in tags:
            rc = z[f"{t}_{k}_rc"]; dG = z[f"{t}_dG"][rc[:, 0], rc[:, 1]]
            data.append(100 * np.abs(dG[np.isfinite(dG)]))
        ax.boxplot(data, tick_labels=[lab[t] for t in tags], showfliers=False) if int(matplotlib.__version__.split(".")[1]) >= 9 else ax.boxplot(data, labels=[lab[t] for t in tags], showfliers=False)
        ax.set_yscale("symlog", linthresh=10); ax.tick_params(labelsize=7); ax.set_title(f"{nm}: |결과 − 참값| (cm, 이 시점)", fontsize=9)
        for xi, d in enumerate(data):
            ax.text(xi + 1, ax.get_ylim()[1] * 0.8 if ax.get_ylim()[1] > 0 else 1, f"n={len(d)}", fontsize=6, ha="center")
    ax = fig.add_subplot(gs[4, 5])
    rc = z[f"{key0}_c3_undetermined_rc"]; gP = z[f"{key0}_gP"][rc[:, 0], rc[:, 1]]
    ax.hist(100 * gP[np.isfinite(gP)], bins=60, range=(-300, 300), color="#4575b4")
    ax.set_title("미판정 픽셀: 참값 − 사전 정보 (cm, 이 시점)", fontsize=9); ax.tick_params(labelsize=7)
fig.savefig(out_png, dpi=80, bbox_inches="tight")
print("written", out_png)
