"""PHD-MAIN-PHOTOFIG-v1 [사용자 요청, 그리는 법 견본] R1 wall 19 in the forms of related work (jointbuildgs:dev, CPU; photofig_v1_proto.json):
  top row     the training photo of the chosen view and the TSDF meshes of three results ray-cast from the same camera pose at 4x pixels
              (Open3D RaycastingScene), grey shading by the face normal and a key light, dark lines at depth steps > 0.2 m
  bottom row  wall 19 unrolled (the LoD2 plane seen from outside): each 0.25 m patch of the evaluation range filled by the median of
              'result - GT' over its GT points (the new distance metric's per-point distance x sign, + outside; dist npz s_*), the first
              column = GT - LoD2 (region file gt_med); seven bins, |d| <= 0.2 m white, < 3 points grey
  bars        the face's missing-area recall (0.2 m) from tables/fig3_r1.json and fig8_r1.json (the delivered numbers)
  then a side-by-side PNG with the delivered figure 3.
  python f9_proto.py   -> /docs/figures/photo_proto_r1_wall19.png|pdf|json, photo_proto_r1_wall19_vs_fig3.png, /docs/tables/proto_r1_wall19.json
scientific_verdict: null"""
import time
from pathlib import Path

import numpy as np
from matplotlib.collections import PolyCollection
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

import p0_places as P0
import pf_geo as G
from pf_common import DOCS, FT, PF, REPO, S1, SD, jdump, jl, log, now

SITE, PRIOR, EXT = "R1rep_b10", "LoD2", 19
DENSE_IMG = Path("/art/phase-payloads/p0-audit/data/work/mvs/colmap_dense/images")
RUNS = {"지금 방법 씨앗 0": (S1 / "stage1" / SITE / "prop_LoD2_s0", "prop_LoD2_s0"),
        "결측 지키기": (FT / "runs" / SITE / "fixB_LoD2_s0", "fixB_LoD2_s0"),
        "폭 좁히기(기록 셈)": (FT / "runs" / SITE / "fixAT_LoD2_s0", "fixAT_LoD2_s0")}
SCALE = 4
LIGHT = np.array([-0.35, -0.55, -0.76]); LIGHT /= np.linalg.norm(LIGHT)
HEAD = np.array([0.0, 0.0, -1.0])                     # [그리는 법만 바꿈, 첫 그림 뒤] mostly a headlight: the wall seen at 59 deg was dark under the key light
EDGE_M = 1.0                                          # [그리는 법만 바꿈, 첫 그림 뒤] 0.2 m drew the mesh speckle as dark dots
CHANGES = ["빛 = 0.65 x 카메라 쪽 + 0.35 x 왼쪽 위 앞(처음: 왼쪽 위 앞만)", "단차 선 = 이웃 화소와 1.0 m 넘게 다른 곳(처음: 0.2 m)",
           "결측 영역 윤곽 = 흩어진 결측 패치를 닫기(위 줄 패치 크기의 1.5배, 아래 줄 0.5 m)와 구멍 메우기로 한 덩어리로 묶은 선",
           "범례를 칸 지도와 막대 사이의 따로 한 줄로", "제목 = 그린 뒤 이 그림에서 보이는 것으로 쓴 문장"]


def dist_file(res):
    for b in (FT / "dist", SD / "dist"):
        f = b / f"{SITE}_{PRIOR}__{res}.npz"
        if f.exists():
            return f
    raise FileNotFoundError(res)


def quads(U, idx):
    h = 0.5 * float(U["sp"])
    c, t1, t2 = U["loc_center"][idx].astype(np.float64), U["loc_t1"][idx].astype(np.float64), U["loc_t2"][idx].astype(np.float64)
    return np.stack([c - h * t1 - h * t2, c + h * t1 - h * t2, c + h * t1 + h * t2, c - h * t1 + h * t2], 1)   # [N, 4, 3]


def project_native(V, k, X):
    fx, fy, cx, cy = V.K0
    Xc = X @ V.R(k).T + V.t(k)
    return fx * Xc[:, 0] / Xc[:, 2] + cx, fy * Xc[:, 1] / Xc[:, 2] + cy, Xc[:, 2]


def shade(V, k, mesh, box_px, s):
    import open3d as o3d
    Vm, Fm, info = G.read_ply_mesh_box(mesh, box_xy, margin=5.0)
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.core.Tensor(Vm.astype(np.float32)), o3d.core.Tensor(Fm.astype(np.uint32)))
    u0, v0, u1, v1 = box_px
    W, H = int(round((u1 - u0) * s)), int(round((v1 - v0) * s))
    fx, fy, cx, cy = V.K0
    uu = u0 + (np.arange(W) + 0.5) / s; vv = v0 + (np.arange(H) + 0.5) / s
    xn = (uu[None, :] - cx) / fx; yn = (vv[:, None] - cy) / fy
    dc = np.stack([np.broadcast_to(xn, (H, W)), np.broadcast_to(yn, (H, W)), np.ones((H, W))], -1)
    dc /= np.linalg.norm(dc, axis=-1, keepdims=True)
    Rk = V.R(k); dw = dc @ Rk                                      # camera -> world (R^T d)
    C = V.C(k)
    rays = np.concatenate([np.broadcast_to(C, (H, W, 3)), dw], -1).reshape(-1, 6).astype(np.float32)
    out = sc.cast_rays(o3d.core.Tensor(rays))
    t = out["t_hit"].numpy().reshape(H, W).astype(np.float64)
    nw = out["primitive_normals"].numpy().reshape(H, W, 3).astype(np.float64)
    flip = (nw * dw).sum(-1) > 0
    nw[flip] *= -1
    nc = nw @ Rk.T                                                  # world -> camera
    img = 0.2 + 0.8 * (0.65 * np.clip(nc @ HEAD, 0, 1) + 0.35 * np.clip(nc @ LIGHT, 0, 1))
    hit = np.isfinite(t)
    img[~hit] = 1.0
    tt = np.where(hit, t, 1e9)
    edge = np.zeros_like(hit)
    edge[:, :-1] |= np.abs(tt[:, 1:] - tt[:, :-1]) > EDGE_M
    edge[:-1, :] |= np.abs(tt[1:, :] - tt[:-1, :]) > EDGE_M
    img[edge & hit] = 0.35
    return img, dict(mesh=info, hit_share=float(hit.mean()), size=[W, H])


def main():
    global box_xy
    t0 = time.time()
    C = jl(REPO / "configs/phd/main_photofig_v1/photofig_v1_proto.json")
    P = C["place"]; view = P["view"]
    V = G.views(); k = G.vkey(view)
    assert (V.W0, V.H0) == (1400, 1013), (V.W0, V.H0)
    R = P0.region(SITE, PRIOR); U = P0.store(SITE, PRIOR)
    se = R["surf_ext"].astype(int); ev = R["in_eval"].astype(bool); code = R["code_ext_v3"].astype(int)
    face = np.nonzero(ev & (se == EXT))[0]
    mp = np.nonzero(ev & (se == EXT) & np.isin(code, [4, 13]))[0]
    Qm = quads(U, mp)
    # ---- top row: crop from the missing quads, +60 % per side
    u, v, z = project_native(V, k, Qm.reshape(-1, 3))
    du, dv = u.max() - u.min(), v.max() - v.min()
    u0, u1 = max(u.min() - 0.6 * du, 0), min(u.max() + 0.6 * du, V.W0); v0, v1 = max(v.min() - 0.6 * dv, 0), min(v.max() + 0.6 * dv, V.H0)
    u0, v0, u1, v1 = int(np.floor(u0)), int(np.floor(v0)), int(np.ceil(u1)), int(np.ceil(v1))
    xy = U["loc_center"][mp][:, :2]
    box_xy = [float(xy[:, 0].min() - 15), float(xy[:, 1].min() - 15), float(xy[:, 0].max() + 15), float(xy[:, 1].max() + 15)]
    photo = np.asarray(Image.open(DENSE_IMG / f"{k if k.endswith('.JPG') else k + '.JPG'}").convert("RGB"))[v0:v1, u0:u1]
    Wv, Hv = int(round((u1 - u0) * SCALE)), int(round((v1 - v0) * SCALE))
    mask = Image.new("L", (Wv, Hv), 0); dr = ImageDraw.Draw(mask)
    for q in Qm:
        qu, qv, _ = project_native(V, k, q)
        dr.polygon([((a - u0) * SCALE, (b - v0) * SCALE) for a, b in zip(qu, qv)], fill=1)
    mask = np.asarray(mask).astype(bool)
    from scipy import ndimage
    qpx = float(np.sqrt(mask.sum() / max(len(Qm), 1)))                 # one patch, in shown pixels
    rr = max(int(round(1.5 * qpx)), 1); yy, xx = np.mgrid[-rr:rr + 1, -rr:rr + 1]
    mask = ndimage.binary_fill_holes(ndimage.binary_closing(mask, structure=(xx ** 2 + yy ** 2) <= rr * rr, iterations=1)).astype(float)
    shaded, sinfo = {}, {}
    for name, (run, _) in RUNS.items():
        shaded[name], sinfo[name] = shade(V, k, run / "post/mesh_tsdf.ply", (u0, v0, u1, v1), SCALE)
        log("shade", name, sinfo[name])
    # ---- bottom row: wall 19 unrolled
    n_out = np.asarray(P["outward_normal"], np.float64); n_out[2] = 0; n_out /= np.linalg.norm(n_out)
    right = np.cross(-n_out, [0.0, 0.0, 1.0]); right /= np.linalg.norm(right)
    c0 = U["loc_center"][mp].astype(np.float64).mean(0)
    def sh(X):
        return np.column_stack([(X[..., :2] - c0[:2]) @ right[:2], X[..., 2]]) if X.ndim == 2 else np.stack([(X[..., :2] - c0[:2]) @ right[:2], X[..., 2]], -1)
    Qf = quads(U, face); SHf = sh(Qf); cf = sh(U["loc_center"][face].astype(np.float64))
    cm = sh(U["loc_center"][mp].astype(np.float64))
    win = [cm[:, 0].min() - 3, cm[:, 0].max() + 3, cm[:, 1].min() - 3, cm[:, 1].max() + 3]
    inw = (cf[:, 0] >= win[0]) & (cf[:, 0] <= win[1]) & (cf[:, 1] >= win[2]) & (cf[:, 1] <= win[3])
    fidx = face[inw]; SHw = SHf[inw]
    vals = {"참값 − LoD2": R["gt_med"][fidx].astype(np.float64)}
    npts = {}
    for name, (_, res) in RUNS.items():
        d = np.load(dist_file(res))
        pa = d["s_patch"].astype(np.int64); ok = pa >= 0
        sg = d["s_d"].astype(np.float64) * np.where(d["s_sign"] == 0, 1, d["s_sign"])
        order = np.argsort(pa[ok], kind="stable"); pas = pa[ok][order]; sgs = sg[ok][order]
        lo = np.searchsorted(pas, fidx, "left"); hi = np.searchsorted(pas, fidx, "right")
        med = np.full(len(fidx), np.nan); cnt = hi - lo
        for i in np.nonzero(cnt >= 3)[0]:
            med[i] = np.median(sgs[lo[i]:hi[i]])
        vals[name + " − 참값"] = med; npts[name] = int(cnt.sum())
    bins = C["bottom_row"]["bins_m"]; cols = C["bottom_row"]["colours"]; nog = C["bottom_row"]["no_gt"]
    def colour(x):
        return nog if not np.isfinite(x) else cols[int(np.searchsorted(bins, x, "right"))]
    # outline of the missing patches on a 5 cm grid (Chebyshev distance to a missing centre <= sp/2)
    gs_ = np.arange(win[0], win[1], 0.05); gh_ = np.arange(win[2], win[3], 0.05)
    GG = np.stack(np.meshgrid(gs_, gh_), -1).reshape(-1, 2)
    dd, _ = cKDTree(cm).query(GG, p=np.inf)
    omask = (dd <= 0.5 * float(U["sp"])).reshape(len(gh_), len(gs_))
    yy2, xx2 = np.mgrid[-10:11, -10:11]
    omask = ndimage.binary_fill_holes(ndimage.binary_closing(omask, structure=(xx2 ** 2 + yy2 ** 2) <= 100)).astype(float)
    # ---- bars (the delivered numbers)
    T3 = jl(DOCS / "tables/fig3_r1.json")["results"]; T8 = jl(DOCS / "tables/fig8_r1.json")["results"]
    bars = [("지금 방법 씨앗 0", T3["지금 방법 씨앗 0"]), ("지금 방법 씨앗 1", T3["지금 방법 씨앗 1"]), ("결측 지키기", T3["결측 지키기"]), ("폭 좁히기(기록 셈)", T8["폭 좁히기(기록 셈)"])]
    # ---- draw
    plt = G.setup_plt()
    from matplotlib.patches import Patch, Rectangle
    aspect_top = Hv / Wv; aspect_bot = (win[3] - win[2]) / (win[1] - win[0])
    colw = 4.0
    fig = plt.figure(figsize=(4 * colw + 0.6, colw * aspect_top + colw * aspect_bot + 3.2))
    gsp = fig.add_gridspec(4, 4, height_ratios=[colw * aspect_top, colw * aspect_bot, 0.35, 1.5], hspace=0.22, wspace=0.05)
    heads = [f"실사진 (영상 {view.split('_')[-2]})", "지금 방법 (씨앗 0)", "결측 지키기", "폭 좁히기(기록 셈)"]
    for j, nm in enumerate([None] + list(RUNS)):
        ax = fig.add_subplot(gsp[0, j])
        if nm is None:
            ax.imshow(photo, extent=(0, Wv, Hv, 0), interpolation="bicubic")
        else:
            ax.imshow(shaded[nm], cmap="gray", vmin=0, vmax=1, interpolation="nearest")
        ax.contour(mask, levels=[0.5], colors=["#ffffff"], linewidths=3.0)
        ax.contour(mask, levels=[0.5], colors=["#000000"], linewidths=1.6, linestyles="--")
        ax.set_xlim(0, Wv); ax.set_ylim(Hv, 0); ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(heads[j], fontsize=11)
    btitles = ["참값 − LoD2", "지금 방법 − 참값", "결측 지키기 − 참값", "기록 셈 − 참값"]
    keys = ["참값 − LoD2"] + [n + " − 참값" for n in RUNS]
    within = {"지금 방법 씨앗 0": T3["지금 방법 씨앗 0"]["patches_within_0_2"], "결측 지키기": T3["결측 지키기"]["patches_within_0_2"], "폭 좁히기(기록 셈)": T8["폭 좁히기(기록 셈)"]["patches_within_0_2"]}
    for j, key in enumerate(keys):
        ax = fig.add_subplot(gsp[1, j])
        pc = PolyCollection(SHw, facecolors=[colour(x) for x in vals[key]], edgecolors="none")
        ax.add_collection(pc)
        ax.contour(gs_, gh_, omask, levels=[0.5], colors=["#000000"], linewidths=1.6, linestyles="--")
        ax.set_xlim(win[0], win[1]); ax.set_ylim(win[2], win[3]); ax.set_aspect("equal")
        ax.set_title(btitles[j], fontsize=11)
        if j == 0:
            ax.set_ylabel("높이 (m)"); ax.set_xlabel("벽을 따라 (m)")
        else:
            ax.set_yticklabels([])
            nm = list(RUNS)[j - 1]
            ax.text(0.02, 0.02, f"결측 칸 0.2 m 안 {within[nm]} / {len(mp)}", transform=ax.transAxes, fontsize=9, bbox=dict(fc="w", ec="none", alpha=0.85))
    labs = ["0.6 m보다 안쪽", "0.4~0.6 m 안쪽", "0.2~0.4 m 안쪽", "±0.2 m 안", "0.2~0.4 m 바깥", "0.4~0.6 m 바깥", "0.6 m보다 바깥"]
    hand = [Patch(fc=c_, ec="#999999", lw=0.4, label=l_) for c_, l_ in zip(cols, labs)] + [Patch(fc=nog, ec="#999999", lw=0.4, label="참값 없음"),
            Patch(fc="none", ec="#000000", ls="--", lw=1.4, label="결측 영역")]
    axl = fig.add_subplot(gsp[2, :]); axl.axis("off")
    axl.legend(handles=hand, loc="center", ncol=9, fontsize=9, frameon=False)
    axb = fig.add_subplot(gsp[3, :])
    bc = {"지금 방법 씨앗 0": "#bdbdbd", "지금 방법 씨앗 1": "#bdbdbd", "결측 지키기": "#1f77b4", "폭 좁히기(기록 셈)": "#2ca02c"}
    for i, (nm, r) in enumerate(bars):
        x = 100 * r["r02_face"]
        axb.barh(i, x, color=bc[nm], height=0.6); axb.text(x + 1, i, f"{x:.1f} %", va="center", fontsize=9)
    axb.set_yticks(range(len(bars))); axb.set_yticklabels([b[0] for b in bars], fontsize=9); axb.invert_yaxis()
    axb.set_xlim(0, 105); axb.set_xlabel(f"벽 19 결측 재현율(0.2 m) — 참값 행 {bars[0][1]['rows_c4_face']}개"); axb.spines[["top", "right"]].set_visible(False)
    title = "R1 벽 19 — 결측 기둥(점선)에서 지금 방법의 면은 벽 바깥으로 나오고(빨강), 결측 지키기는 참값을 따라간다(흰색)"
    fig.suptitle(title, fontsize=14, y=0.995)
    for ext in ("png", "pdf"):
        fig.savefig(DOCS / "figures" / f"photo_proto_r1_wall19.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    # ---- side by side with the delivered figure 3
    A = Image.open(DOCS / "figures/photo_fig3_r1.png").convert("RGB"); B = Image.open(DOCS / "figures/photo_proto_r1_wall19.png").convert("RGB")
    h = max(A.size[1], B.size[1])
    A = A.resize((int(A.size[0] * h / A.size[1]), h)); B = B.resize((int(B.size[0] * h / B.size[1]), h))
    M = Image.new("RGB", (A.size[0] + B.size[0] + 40, h + 70), "white"); M.paste(A, (0, 70)); M.paste(B, (A.size[0] + 40, 70))
    from PIL import ImageFont
    f_ = ImageFont.truetype("/fonts/NotoSansCJK-Regular.ttc", 40)
    d_ = ImageDraw.Draw(M); d_.text((20, 10), "지금 그림 3", fill="black", font=f_); d_.text((A.size[0] + 60, 10), "견본: 같은 시점 음영 + 벽 정면 칸 지도", fill="black", font=f_)
    M.save(DOCS / "figures/photo_proto_r1_wall19_vs_fig3.png")
    out = dict(view=view, crop_native_px=[u0, v0, u1, v1], scale=SCALE, shading=sinfo, window_m=[float(x) for x in win], patches_in_window=int(len(fidx)),
               missing_patches=int(len(mp)), gt_points_used=npts, cells_with_value={kk: int(np.isfinite(vv).sum()) for kk, vv in vals.items()},
               missing_cells_within_0_2_by_median={kk: int((np.abs(vv[np.isin(fidx, mp)]) <= 0.2).sum()) for kk, vv in vals.items()},
               bars={b[0]: b[1]["r02_face"] for b in bars}, title=title, changes_after_first_draw=CHANGES, seconds=round(time.time() - t0, 1), made=now(), scientific_verdict=None)
    jdump(DOCS / "tables/proto_r1_wall19.json", out)
    jdump(DOCS / "figures/photo_proto_r1_wall19.json", dict(title=title, view=view, crop_native_px=[u0, v0, u1, v1], made=now(), scientific_verdict=None))
    log("done", out["seconds"], out["cells_with_value"], out["missing_cells_within_0_2_by_median"])


box_xy = None
if __name__ == "__main__":
    main()
