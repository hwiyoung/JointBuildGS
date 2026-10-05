"""Inspection figures (§7) from the independent reproduction outputs. Same view (0005), same colour
scales as stage 1: residual −1.5…+1.5 m diverging, width-out map red/white/gray."""
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from PIL import Image

# Korean glyphs: host Noto Sans CJK mounted read-only at /fonts (renders Hangul + Latin; DejaVu lacks Hangul,
# DroidSansFallback lacks Latin)
for _fp in ["/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Medium.ttc", "/fonts/DroidSansFallbackFull.ttf"]:
    if Path(_fp).exists():
        fm.fontManager.addfont(_fp)
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=_fp).get_name()
        break
matplotlib.rcParams["axes.unicode_minus"] = False

OUT = Path("/insp")
FIG = OUT / "figures"
FIG.mkdir(exist_ok=True)
C = json.loads((OUT / "repro/checks.json").read_text())
Z = np.load(OUT / "repro/fig_arrays.npz")
TASK = Path("/artifacts/JointBuildGS/phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1")
VIEW = "DJI_20241217101305_0005_D"
edges = np.array(C["hist_edges"])
centers = 0.5 * (edges[:-1] + edges[1:])
KO = {"nominal": "정상", "biased": "편향+1.0 m", "L": "L(ALS)", "M": "M(LoD2)"}


def ov(prior, cond, pool, axis):
    return C["overall"][f"{prior}|{cond}|{pool}|{axis}"]


# ---- Figure 1: residual histograms, prior x scene, with m2, ±τ, ±4τ (prompt pool = building faces, camera-Z)
for pool, tag in [("bldg", "건물면(지붕+벽면)"), ("roof", "지붕")]:
    fig, axs = plt.subplots(2, 2, figsize=(12, 7), dpi=110, sharex=True)
    for i, prior in enumerate("LM"):
        for j, cond in enumerate(["nominal", "biased"]):
            ax = axs[i, j]
            h = C["hist"][f"{prior}|{cond}|{pool}|camz"]
            n = sum(h["counts"]) + h["under"] + h["over"]
            ax.plot(centers, np.array(h["counts"]) / max(n, 1), color="#1f5fbf" if cond == "nominal" else "#c62828", lw=1.2)
            st = ov(prior, cond, pool, "camz")
            ref = ov(prior, "nominal", pool, "camz")
            ax.axvline(st["m2"], color="k", lw=0.8, label=f"m2={st['m2']:.3f}")
            for k, ls in [(1, "-"), (4, ":")]:
                for sgn in (-1, 1):
                    ax.axvline(ref["m2"] + sgn * k * ref["tau"], color="#444", lw=1.6 if k == 1 else 1.0, ls=ls)
            ax.set_title(f"{KO[prior]} {KO[cond]} — {tag}, 카메라Z 잔차  n={st['n']:,}  m2={st['m2']:.3f}  s2={st['s2']:.3f}  τ={ref['tau']:.3f} (정상 기준)", fontsize=9)
            ax.set_xlim(-3, 3)
            ax.grid(alpha=0.3)
    for ax in axs[1]:
        ax.set_xlabel("r = MVS − prior (m)")
    fig.suptitle("그림 1: 잔차 히스토그램 — 실선 굵은 세로선 ±τ, 점선 ±4τ (정상 장면 값), 검정 얇은선 m2", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / f"fig1_hist_{pool}.png")
    plt.close(fig)

# ---- Figure 2/3: width-out maps (τ-based, prompt definition) for the biased and nominal scenes, view 0005
A = Z["A"]
img = Image.open(TASK / "out/viewer_png/views" / f"{VIEW}_image.png")
vw, vh = img.size
Hf, Wf = A.shape
ys = np.minimum(((np.arange(vh) + 0.5) * Hf / vh).astype(int), Hf - 1)
xs = np.minimum(((np.arange(vw) + 0.5) * Wf / vw).astype(int), Wf - 1)


def small(a):
    return a[np.ix_(ys, xs)]


def outmap(prior, cond, ref_pool="bldg"):
    r = Z[f"{prior}_{cond}_r"].astype(np.float32)
    region = Z[f"region_{prior}"]
    ref = ov(prior, "nominal", ref_pool, "camz")
    yes = np.isfinite(r)
    roofwall = (region == 1) | (region == 2)
    out = yes & roofwall & (np.abs(r - ref["m2"]) > ref["tau"])
    out3 = yes & roofwall & (np.abs(r - ref["m2"]) > 3 * ref["s2"])
    return out, out3, yes, roofwall


def rgb_out(out, yes, dom):
    rgb = np.full(out.shape + (3,), 150, np.uint8)
    rgb[yes] = 255
    rgb[out] = (220, 30, 30)
    rgb[~dom] = 70
    return rgb


for cond, fname, title in [("biased", "fig2_widthout_biased.png", "그림 2: 편향 장면 폭 밖 픽셀(τ 기준, 정상 장면 m2·τ) — 빨강 폭 밖, 흰 예(폭 안), 회색 아니오, 진회색 건물면 밖"),
                           ("nominal", "fig3_widthout_nominal.png", "그림 3: 정상 장면 폭 밖 픽셀(τ 기준) — 같은 시점·같은 색")]:
    fig, axs = plt.subplots(2, 3, figsize=(16, 8.4), dpi=100)
    for i, prior in enumerate("LM"):
        out, out3, yes, dom = outmap(prior, cond)
        axs[i, 0].imshow(img)
        axs[i, 0].set_title(f"{KO[prior]} {KO[cond]} — 영상", fontsize=9)
        axs[i, 1].imshow(rgb_out(small(out), small(yes), small(dom)))
        axs[i, 1].set_title(f"폭 밖(|r−m2|>τ={ov(prior,'nominal','bldg','camz')['tau']:.2f} m): 건물면 예 픽셀의 {100*out.sum()/max((yes&dom).sum(),1):.1f}%", fontsize=9)
        axs[i, 2].imshow(rgb_out(small(out3), small(yes), small(dom)))
        axs[i, 2].set_title(f"참고 3s 기준(s2={ov(prior,'nominal','bldg','camz')['s2']:.3f}): {100*out3.sum()/max((yes&dom).sum(),1):.1f}%", fontsize=9)
        for ax in axs[i]:
            ax.axis("off")
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / fname)
    plt.close(fig)

# ---- Figure 4: zoom on the injected roof (biased, L and M), residual maps and width-out, roof crop box from region
region = Z["region_L"]
rr, cc = np.where(region == 1)
y0, y1, x0, x1 = rr.min(), rr.max(), cc.min(), cc.max()
fig, axs = plt.subplots(2, 3, figsize=(16, 6.5), dpi=100)
for i, prior in enumerate("LM"):
    r = Z[f"{prior}_biased_r"].astype(np.float32)[y0:y1, x0:x1]
    rv = Z[f"{prior}_biased_rv"].astype(np.float32)[y0:y1, x0:x1]
    out, out3, yes, dom = outmap(prior, "biased")
    axs[i, 0].imshow(np.asarray(img.resize((Wf, Hf)))[y0:y1, x0:x1])
    axs[i, 0].set_title(f"{KO[prior]} 편향 — 주입 지붕 확대(영상)", fontsize=9)
    im1 = axs[i, 1].imshow(r, cmap="RdBu_r", vmin=-1.5, vmax=1.5)
    axs[i, 1].set_title("카메라Z 잔차 r (−1.5…+1.5 m)", fontsize=9)
    im2 = axs[i, 2].imshow(rv, cmap="RdBu_r", vmin=-1.5, vmax=1.5)
    axs[i, 2].set_title(f"연직 잔차 r_v (지붕만) 중앙값 {np.nanmedian(rv):.3f} m (float16 사본, ±0.0005)", fontsize=9)
    for ax in axs[i]:
        ax.axis("off")
fig.colorbar(im2, ax=axs, fraction=0.02, label="m")
fig.suptitle("그림 4: 편향 장면 주입 지붕 확대 — 카메라Z 잔차는 시선 경사에 따라 1.1~4 m, 연직 잔차는 ≈1 m로 고르다", fontsize=10)
fig.savefig(FIG / "fig4_injected_roof_zoom.png")
plt.close(fig)

# ---- Figure 5: cross-sections across the roof (two image rows with most roof pixels), τ band
rows_roof = (region == 1).sum(1)
cand = np.argsort(rows_roof)[::-1]
r_a = int(cand[0])
r_b = int(next(r for r in cand if abs(int(r) - r_a) > 0.25 * (y1 - y0)))
fig, axs = plt.subplots(2, 2, figsize=(15, 7), dpi=100, sharex="col")
for j, prior in enumerate("LM"):
    ref = ov(prior, "nominal", "roof", "camz")
    refv = ov(prior, "nominal", "roof", "vert")
    for i, row in enumerate([r_a, r_b]):
        ax = axs[i, j]
        xsel = np.where(region[row] == 1)[0]
        for cond, col in [("nominal", "#1f5fbf"), ("biased", "#c62828")]:
            r = Z[f"{prior}_{cond}_r"].astype(np.float32)[row]
            rv = Z[f"{prior}_{cond}_rv"].astype(np.float32)[row]
            ax.plot(xsel, r[xsel], ".", ms=1.5, color=col, alpha=0.6, label=f"{KO[cond]} r(카메라Z)")
            ax.plot(xsel, rv[xsel], ".", ms=1.5, color=col, alpha=0.25, label=f"{KO[cond]} r_v(연직)")
        ax.axhspan(ref["m2"] - ref["tau"], ref["m2"] + ref["tau"], color="#999", alpha=0.25, label=f"허용 구간 ±τ={ref['tau']:.2f} (카메라Z, 지붕 풀)")
        ax.axhline(ref["m2"] + 1.0, color="k", lw=0.6, ls="--", label="m2+1.0 m")
        ax.set_ylim(-1.5, 4.5)
        ax.set_title(f"{KO[prior]} — 이미지 행 {row} (지붕 픽셀 {len(xsel):,})", fontsize=9)
        ax.grid(alpha=0.3)
        if i == 0 and j == 0:
            ax.legend(fontsize=7, loc="upper right", markerscale=4)
axs[1, 0].set_xlabel("열 (픽셀)")
axs[1, 1].set_xlabel("열 (픽셀)")
fig.suptitle("그림 5: 주입 지붕을 가로지르는 잔차 단면 — 정상(파랑)은 허용 구간 안, 편향(빨강)은 밖; 연직 잔차는 +1 m 선 근처", fontsize=10)
fig.tight_layout()
fig.savefig(FIG / "fig5_cross_sections.png")
plt.close(fig)

# ---- Figure 6: coverage maps (A over roof/wall) and per-view coverage
fig, axs = plt.subplots(1, 3, figsize=(16, 4.6), dpi=100)
axs[0].imshow(img)
axs[0].set_title("영상", fontsize=9)
regL = small(region)
Asm = small(A)
rgb = np.full(regL.shape + (3,), 40, np.uint8)
rgb[(regL == 1) & (Asm == 1)] = (230, 120, 30)
rgb[(regL == 1) & (Asm == 0)] = (90, 45, 10)
rgb[(regL == 2) & (Asm == 1)] = (60, 130, 220)
rgb[(regL == 2) & (Asm == 0)] = (20, 45, 80)
axs[1].imshow(rgb)
axs[1].set_title("지붕(주황)/벽면(파랑): 밝음 = A 예, 어두움 = A 아니오", fontsize=9)
axs[0].axis("off")
axs[1].axis("off")
import csv
cov = list(csv.DictReader((OUT / "repro/coverage_per_view.csv").open()))
for prior, col, mk in [("L", "#e6781e", "o"), ("M", "#3c82dc", "x")]:
    for pool, ls in [("roof", "-"), ("wall", "--")]:
        v = [float(r["coverage"]) for r in cov if r["prior"] == prior and r["cond"] == "nominal" and r["pool"] == pool]
        axs[2].plot(range(len(v)), v, ls=ls, marker=mk, ms=4, color=col, label=f"{prior} {pool}")
axs[2].set_ylim(0, 1)
axs[2].set_xlabel("시점 index")
axs[2].set_ylabel("A 예 비율")
axs[2].legend(fontsize=7)
axs[2].grid(alpha=0.3)
axs[2].set_title("시점별 커버리지 (L과 M 겹침 = prior 무관)", fontsize=9)
fig.suptitle("그림 6: 관측 신뢰도 지도 A의 커버리지", fontsize=10)
fig.tight_layout()
fig.savefig(FIG / "fig6_coverage.png")
plt.close(fig)

# ---- Figure 7: viewer panel-3 crops from the derived snapshot pages
for P in "LM":
    p = FIG / f"viewer_full_{P}_biased.png"
    if p.exists():
        im = Image.open(p)
        w, h = im.size
        im.crop((0, int(h * 0.62), w, h)).save(FIG / f"fig7_viewer_panel3_{P}_biased.png")
print("figures written:", sorted(x.name for x in FIG.iterdir()))
