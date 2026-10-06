"""PHD-MAIN-PREP-MEASURE-v1 step 08 (jointbuildgs:dev, CPU): GeoGS Fig. 6(a) regions against our ranges and boxes (5.8).

  python step08_geogs_regions.py

Inputs: step08/inputs/fig6a_page8_300dpi_crop.png (paper Fig. 6(a) with its vector region boxes, see inputs/README.txt),
survey v1 colour ortho (rgb_mvs, 0.5 m), step01/ranges.json, step06/box_ranges.json.
The figure is an oblique view; the 9 dashed boxes and 4 ground control points (street intersections around the campus
block) are read by the analyst on the figure frame and on our uv ortho. A ground-plane homography maps the boxes to uv:
approximate (manual picks, building lean of the oblique view), analyst judgment, human review pending.
Outputs: step08/geogs_regions.json, step08/fig_geogs_regions_map.png, step08/fig_geogs_regions_check.png.
scientific_verdict: null."""
import json

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from shapely.geometry import Polygon, box as sbox

from common import OUT, SHIFT, SURVEY, jdump, uv_to_xy, xy_to_uv

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

D = OUT / "step08"
# analyst picks, figure frame (pixels of Fig. 6(a) image 0) -> uv (m) read on the uv ortho (0.5 m pixels)
CP_FIG = np.float32([[462, 125], [1322, 128], [398, 762], [1345, 762]])
CP_UV = np.float32([[-144.0, -93.5], [107.5, -89.0], [-145.0, 116.0], [106.0, 120.0]])
CP_NAME = ["top street x left street", "top street x right street", "bottom street x left street", "bottom street x right street"]
# dashed region boxes on the figure frame (x0, y0, x1, y1), read on the vector render
REG = {1: (1088, 640, 1328, 760), 2: (715, 415, 1075, 555), 3: (455, 395, 555, 705), 4: (175, 165, 420, 550),
       5: (455, 222, 560, 360), 6: (520, 135, 775, 205), 7: (815, 135, 1045, 270), 8: (1270, 165, 1385, 390),
       9: (1270, 410, 1385, 600)}
H = cv2.getPerspectiveTransform(CP_FIG, CP_UV)
Hi = np.linalg.inv(H)


def to_uv(p):
    q = H @ np.array([p[0], p[1], 1.0]); return q[:2] / q[2]


def to_fig(p):
    q = Hi @ np.array([p[0], p[1], 1.0]); return q[:2] / q[2]


def main():
    ranges = json.loads((OUT / "step01/ranges.json").read_text())
    boxes = json.loads((OUT / "step06/box_ranges.json").read_text()) if (OUT / "step06/box_ranges.json").exists() else {}
    ours = {}
    for k, r in ranges.items():
        if r["kind"] == "uv_box":
            ours[k] = sbox(r["u_m"][0], r["v_m"][0], r["u_m"][1], r["v_m"][1])
        elif k == "B0":
            ours[k] = Polygon(xy_to_uv(np.asarray(r["polygon_local"])))
        elif k == "B0BLD":
            ours[k] = Polygon(xy_to_uv(np.asarray(r["polygon_local"])))
    for k, r in boxes.items():
        ours["box " + k] = sbox(r["u_m"][0], r["v_m"][0], r["u_m"][1], r["v_m"][1])
        if r["band_m"] in (0, 10):
            e = sbox(r["eval_u"][0], r["eval_v"][0], r["eval_u"][1], r["eval_v"][1])
            ours["eval " + r["box"]] = e
    regs = {}
    for k, (x0, y0, x1, y1) in REG.items():
        q = np.array([to_uv(p) for p in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]])
        P = Polygon(q)
        ov = {}
        for name, G in ours.items():
            a = P.intersection(G).area
            if a > 1.0:
                ov[name] = dict(area_m2=round(a, 1), share_of_region=round(a / P.area, 3), share_of_ours=round(a / G.area, 3))
        xy = uv_to_xy(q)
        regs[str(k)] = dict(figure_box_px=[x0, y0, x1, y1], quad_uv=q.round(2).tolist(), quad_epsg25832=(xy + SHIFT[:2]).round(2).tolist(),
                            area_m2=round(P.area, 1), extent_u_m=round(float(q[:, 0].max() - q[:, 0].min()), 1),
                            extent_v_m=round(float(q[:, 1].max() - q[:, 1].min()), 1), overlaps=ov)
    # check: control points are exact (4-point homography); one independent check point
    chk = dict(note="4 control points define the homography exactly (no residual); independent check: the B0 target building front facade "
                    "(uv v = 109.4, LoD2 footprint) maps to figure y = 727-731 px; its base in the figure is at y ~ 735 px (about 1-2 m on the ground)",
               b0_front_corners_fig=[to_fig((30.1, 109.4)).round(1).tolist(), to_fig((96.8, 109.4)).round(1).tolist()])
    out = dict(task_id="PHD-MAIN-PREP-MEASURE-v1", step="08 GeoGS regions (5.8)", scientific_verdict=None,
               source="GeoGS paper Fig. 6(a), PDF page 8 (local copy, sha256 in step08/inputs/paper_pdf.sha256)",
               method="ground-plane homography from 4 street intersections (analyst picks) applied to the 9 dashed boxes read on the figure; "
                      "approximate: manual picks and building lean of the oblique view (boxes enclose roofs and near facades)",
               control_points=[dict(name=n, fig_px=f.tolist(), uv_m=u.tolist()) for n, f, u in zip(CP_NAME, CP_FIG, CP_UV)],
               homography_fig_to_uv=H.tolist(), check=chk, regions=regs,
               analyst_reading="Region 1 covers the B0 target building (DEBY_LOD2_4959323); with the example_scene ground truth name "
                               "'r1_b1_sub002' this reads as Region 1, building 1 (name-based, not confirmed by the authors)")
    jdump(D / "geogs_regions.json", out)
    # ---- map figure (uv ortho)
    Sv = np.load(SURVEY / "derived.npz"); rgb = Sv["rgb_mvs"]
    W, Hh = 1300, 900
    cols, rows = np.meshgrid(np.arange(W), np.arange(Hh))
    u = -260 + 0.5 * cols; v = -200 + 0.5 * rows
    xy = uv_to_xy(np.column_stack([u.ravel(), v.ravel()]))
    E = xy[:, 0] + SHIFT[0]; N = xy[:, 1] + SHIFT[1]
    ix = ((E - 690700.0) / 0.5).astype(int); iy = ((N - 5335820.0) / 0.5).astype(int)
    ok = (ix >= 0) & (ix < rgb.shape[1]) & (iy >= 0) & (iy < rgb.shape[0])
    img = np.full((Hh * W, 3), 255, np.uint8); img[ok] = rgb[iy[ok], ix[ok]]
    img = img.reshape(Hh, W, 3)
    fig, ax = plt.subplots(figsize=(15, 10.5))
    ax.imshow(img, extent=[-260, -260 + 0.5 * W, -200 + 0.5 * Hh, -200], alpha=0.75)
    colors = dict(R1="#1f77b4", R2="#ff7f0e", R3="#2ca02c", R4="#9467bd", R5="#8c564b", B0="#e377c2", SW="#17becf", R3E="#bcbd22")
    for k, G in ours.items():
        if k in colors:
            x_, y_ = G.exterior.xy
            ax.plot(x_, y_, color=colors[k], lw=2.0 if k != "R3E" else 1.0, ls="-" if k != "R3E" else ":")
            ax.text(min(x_) + 2, min(y_) + 6, k, color=colors[k], fontsize=10, weight="bold")
        elif k.startswith("eval "):
            x_, y_ = G.exterior.xy
            ax.plot(x_, y_, color="white", lw=1.2, ls="-")
            ax.text(min(x_) + 1, max(y_) - 2, k[5:], color="white", fontsize=7.5)
    for k, rg in regs.items():
        q = np.array(rg["quad_uv"] + [rg["quad_uv"][0]])
        ax.plot(q[:, 0], q[:, 1], color="red", lw=2.0, ls="--")
        c = q[:-1].mean(0)
        ax.text(c[0], c[1], f"GeoGS {k}", color="red", fontsize=10, weight="bold", ha="center", va="center",
                bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1))
    ax.set_xlabel("u (m)"); ax.set_ylabel("v (m)")
    ax.set_title("GeoGS 그림 6(a)의 아홉 영역(빨강 점선, 근사)과 우리 찾기 범위(색 실선)·사례 상자 평가 범위(흰 선)", fontsize=11)
    fig.savefig(D / "fig_geogs_regions_map.png", dpi=95, bbox_inches="tight"); plt.close(fig)
    # ---- check figure: our ranges back-projected onto the paper figure
    C = cv2.imread(str(D / "inputs/fig6a_page8_300dpi_crop.png"))[:, :, ::-1]
    fig, ax = plt.subplots(figsize=(15, 8.5))
    ax.imshow(C)
    for k, G in ours.items():
        if k in colors:
            uu, vv = G.exterior.xy
            pts = np.array([to_fig((a, b)) for a, b in zip(np.interp(np.linspace(0, len(uu) - 1, 200), np.arange(len(uu)), uu),
                                                          np.interp(np.linspace(0, len(vv) - 1, 200), np.arange(len(vv)), vv))])
            ax.plot(pts[:, 0], pts[:, 1], color=colors[k], lw=1.6)
            ax.text(pts[:, 0].min() + 4, pts[:, 1].min() + 14, k, color=colors[k], fontsize=9, weight="bold")
    ax.plot(CP_FIG[:, 0], CP_FIG[:, 1], "y+", ms=16, mew=2.5)
    ax.set_xlim(0, C.shape[1]); ax.set_ylim(C.shape[0], 0); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title("점검: 우리 범위를 논문 그림 틀로 되돌려 그림(노랑 + = 기준점 네 곳, 지면 기준이라 지붕은 위로 기울어 보임)", fontsize=10)
    fig.savefig(D / "fig_geogs_regions_check.png", dpi=90, bbox_inches="tight"); plt.close(fig)
    print("regions", {k: (r["extent_u_m"], r["extent_v_m"], list(r["overlaps"].keys())[:6]) for k, r in regs.items()})


if __name__ == "__main__":
    main()
