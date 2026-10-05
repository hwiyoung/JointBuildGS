"""Numbers and figures for the table-reading note of the stage-2 intent check (jointbuildgs:dev, CPU). scientific_verdict: null.

  python make_reading.py [--iteration 30000]
Mounts: /s2 (payload; rw for eval/ and dashboard/reading/).

Same pixels, classes and units as eval_intent.py / make_intent_viewer.py: target roof + wall pixels of every rendered view at
training resolution, classes from the stage-1 inputs of the setting (I read with each setting's prior), distances vertical on
roofs and along the face normal on walls, GT = JBGS_GT_SET (default gt_clean, make_gt_clean.py; evaluation only).
1. Instruction x execution on the conflict pixels (the 2x2). The judgment told the result to go to the photo surface.
   right    = the photo is nearer the GT than the prior (|M-G| < |P-G|)
   followed = the result is within tau of the photo (|D-M| <= tau), as the table's 'followed'
   Per setting x region x condition: share of the conflict pixels with GT in each cell and the median |D-G| there.
2. Where each condition puts the pixels of each class: signed result - prior and result - photo (+ = above / outside),
   medians and histograms. The class of a pixel is fixed by the inputs; its 3-D position in the viewer is the condition's
   rendered depth; where several views put points on one spot the front one hides the rest, so the same classes look
   different per condition.
3. One pixel through the four comparisons of the table (--pixel, an index of the viewer's per-setting sample written by
   export_intent_surface_points.py, the same pixel the 3-D view shows with #pick=<index>): class, source errors, followed and
   result error of every condition on one axis.
Outputs: eval/reading_2x2_<it>.csv, eval/reading_positions_<it>.csv, eval/reading_hist_<it>.npz,
dashboard/reading/positions_<setting>.png, dashboard/reading/pixel_<setting>_<index>.png"""
import os
import argparse
import csv
import json
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

GT_SET = os.environ.get("JBGS_GT_SET", "gt_clean")   # evaluation GT maps: gt_clean (visibility + ground datum, make_gt_clean.py) or gt (raw)
S2 = Path("/s2"); MAPS = S2 / "inputs/maps"; FIG = S2 / "dashboard/reading"
SETTINGS = {"M_N": ["P_M_N", "P0_M_N", "O_M_N", "I"], "M_B": ["P_M_B", "P0_M_B", "O_M_B", "I"],
            "L_N": ["P_L_N", "P0_L_N", "I"], "L_B": ["P_L_B", "P0_L_B", "I"]}
NAMES = {"P": "P 판정 켬", "P0": "P0 판정 끔", "O": "O 공식 GeoGS", "I": "I 영상 단독"}
PRIOR_NAME = {"M": "LoD2", "L": "ALS"}
CLASSES = ("agree", "conflict", "unobserved")
CLS_KO = {"agree": "일치", "conflict": "충돌", "unobserved": "못 잼"}
CLS_RGB = {"agree": "#4285f4", "conflict": "#ff9800", "unobserved": "#9c27b0"}
EDGES = np.arange(-150.5, 151.5, 1.0)                     # 1 cm bins for result - prior (cm)
ap = argparse.ArgumentParser()
ap.add_argument("--iteration", type=int, default=30000)
ap.add_argument("--figures-only", action="store_true", help="redraw the figures from eval/reading_hist_<it>.npz")
ap.add_argument("--pixel", type=int, default=101640, help="index in the viewer's per-setting sample (dashboard/surfels)")
ap.add_argument("--pixel-setting", default="M_N")
a = ap.parse_args()
FIG.mkdir(parents=True, exist_ok=True)
for f in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Medium.ttc"):
    if Path(f).exists():
        font_manager.fontManager.addfont(f); plt.rcParams["font.family"] = font_manager.FontProperties(fname=f).get_name(); break
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]
cache = {}


def load(setname, view, size, dtype=np.float32):
    key = (setname, view, size)
    if key not in cache:
        p = MAPS / setname / "raw_depth" / f"{view}.npy"
        x = np.load(p if p.exists() else MAPS / setname / f"{view}.npy")
        cache[key] = cv2.resize(x.astype(np.float32), size, interpolation=cv2.INTER_NEAREST).astype(dtype)
    return cache[key]


def med(x):
    return float(np.median(x)) if x.size else float("nan")


HIST = S2 / "eval" / f"reading_hist_{a.iteration}.npz"
if not a.figures_only:
    rows22, rowspos, hists, refline = [], [], {}, {}
    for setting, conds in SETTINGS.items():
        prior, tau = f"prior_{setting}", f"tau_{setting[0]}"
        for cond in conds:
            rdir = S2 / "eval" / cond / f"render_{a.iteration}"
            views = sorted(json.loads((rdir / "receipt.json").read_text())["views"])
            acc = {}
            for v in views:
                D = np.load(rdir / f"{v}_depth.npy"); size = (D.shape[1], D.shape[0])
                A, M, P, T = load("conf", v, size), load("mvs", v, size), load(prior, v, size), load(tau, v, size)
                G, FV, F = load(GT_SET, v, size), load("fvert", v, size), load("faceid", v, size, np.int32)
                base = (D > 0) & np.isfinite(P) & (P > 0) & np.isfinite(T)
                hasM, hasG = np.isfinite(M) & (M > 0), np.isfinite(G) & (G > 0)
                cls = {"agree": base & (A > 0) & hasM & (np.abs(M - P) <= T), "conflict": base & (A > 0) & hasM & (np.abs(M - P) > T),
                       "unobserved": base & (A <= 0)}
                for region, rm in (("roof", np.isin(F, ROOF)), ("wall", np.isin(F, WALL))):
                    for k, m in cls.items():
                        m = m & rm
                        r = acc.setdefault((region, k), dict(rp=[], rm=[], atP=[], atM=[], pm=[], cells={}))
                        r["rp"].append(((P - D) * FV)[m] * 100)                 # result - prior, cm, + = result above / outside
                        r["rm"].append(((M - D) * FV)[m & hasM] * 100)          # result - photo
                        r["atP"].append((np.abs(D - P) <= T)[m]); r["atM"].append((np.abs(D - M) <= T)[m & hasM])
                        if k == "conflict":
                            r["pm"].append(((P - M) * FV)[m] * 100)             # photo - prior (where the judgment sends it)
                            g = m & hasG
                            right = (np.abs(M - G) < np.abs(P - G))[g]
                            fol = (np.abs(D - M) <= T)[g]
                            err = (np.abs(D - G) * FV)[g] * 100
                            for cell, sel in (("right_followed", right & fol), ("right_not", right & ~fol),
                                              ("wrong_followed", ~right & fol), ("wrong_not", ~right & ~fol)):
                                r["cells"].setdefault(cell, []).append(err[sel])
            for (region, k), r in acc.items():
                rp, rmv = np.concatenate(r["rp"]), np.concatenate(r["rm"])
                atP, atM = np.concatenate(r["atP"]), np.concatenate(r["atM"])
                rowspos.append(dict(iteration=a.iteration, setting=setting, condition=cond, region=region, cls=k, n=int(rp.size),
                                    result_minus_prior_cm=round(med(rp), 1), result_minus_photo_cm=round(med(rmv), 1) if rmv.size else None,
                                    share_at_prior=round(float(atP.mean()), 4) if atP.size else None,           # |D-P| <= tau (table's 'keep')
                                    share_at_photo=round(float(atM.mean()), 4) if atM.size else None))          # |D-M| <= tau (table's 'go')
                hists[(setting, cond, region, k)] = np.histogram(np.clip(rp, EDGES[0] + 0.5, EDGES[-1] - 0.5), EDGES)[0]
                if k == "conflict":
                    refline[(setting, region)] = med(np.concatenate(r["pm"]))
                    n = sum(x.size for y in r["cells"].values() for x in y)
                    out = dict(iteration=a.iteration, setting=setting, condition=cond, region=region, n_conflict_with_gt=n)
                    right = 0
                    for cell in ("right_followed", "right_not", "wrong_followed", "wrong_not"):
                        e = np.concatenate(r["cells"].get(cell, [np.zeros(0)]))
                        out[f"{cell}_share"] = round(e.size / max(n, 1), 4); out[f"{cell}_err_cm"] = round(med(e), 1)
                        right += e.size if cell.startswith("right") else 0
                    out["instruction_right_share"] = round(right / max(n, 1), 4)
                    rows22.append(out)
            print(setting, cond, "done", flush=True)
        cache.clear()

    for name, rows in ((f"reading_2x2_{a.iteration}.csv", rows22), (f"reading_positions_{a.iteration}.csv", rowspos)):
        with (S2 / "eval" / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    np.savez_compressed(HIST, **{"h|" + "|".join(k): v for k, v in hists.items()}, **{"r|" + "|".join(k): np.float64(v) for k, v in refline.items()})
Z = np.load(HIST)
hists = {tuple(k.split("|")[1:]): Z[k] for k in Z.files if k.startswith("h|")}
refline = {tuple(k.split("|")[1:]): float(Z[k]) for k in Z.files if k.startswith("r|")}

# figure: per setting, where each condition put the pixels of each class (result - prior); rows = wall, roof
for setting, conds in SETTINGS.items():
    pn = PRIOR_NAME[setting[0]]
    fig, axes = plt.subplots(2, len(conds), figsize=(4.1 * len(conds), 6.4), sharey="row", squeeze=False)
    ctr = 0.5 * (EDGES[1:] + EDGES[:-1])
    for i, region in enumerate(("wall", "roof")):
        lo, hi = (-60, 40) if region == "wall" else (-50, 60)
        for j, cond in enumerate(conds):
            ax = axes[i, j]
            for k in ("unobserved", "conflict", "agree"):
                h = hists[(setting, cond, region, k)].astype(float)
                if h.sum() == 0:
                    continue
                ax.fill_between(ctr, h / h.sum() * 100, step="mid", color=CLS_RGB[k], alpha=0.35, lw=0)
                ax.step(ctr, h / h.sum() * 100, where="mid", color=CLS_RGB[k], lw=1.2, label=CLS_KO[k])
            ax.axvline(0, color="#1f4e9c", lw=1.4)
            ref = refline[(setting, region)]
            ax.axvline(ref, color="#e65100", lw=1.4, ls="--")
            ax.set_xlim(lo, hi); ax.grid(alpha=0.25)
            if i == 0:
                ax.set_title(f"{NAMES[cond.split('_')[0]]}", fontsize=12)
            if j == 0:
                ax.set_ylabel(("벽" if region == "wall" else "지붕") + "\n픽셀 몫 (%, 칸마다 합 100)", fontsize=10)
            if i == 1:
                ax.set_xlabel(f"결과 − {pn} 면 (cm, + = 위·바깥; 범위 밖은 생략)", fontsize=10)
            tr = ax.get_xaxis_transform()                           # x in cm, y in axes fraction
            ax.text(0.5, 0.97, f" {pn} 면", color="#1f4e9c", fontsize=8.5, va="top", transform=tr)
            ax.text(ref, 0.80, f"충돌 칸 사진\n가운데 {ref:+.0f} ", color="#e65100", fontsize=8.5, va="top",
                    ha="right" if ref < 0 else "left", transform=tr)
    axes[0, 0].legend(loc="upper left", fontsize=9, frameon=False)
    fig.suptitle(f"같은 칸, 다른 자리 — 조건마다 결과 표면이 각 칸 픽셀을 어디에 놓았나 ({pn} · "
                 f"{'정상' if setting[2] == 'N' else '본지붕 +1 m'}, 15시점 전체 픽셀)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(FIG / f"positions_{setting}.png", dpi=110); plt.close(fig)


# figure: one pixel through the four comparisons of the table
def rdbin(path):
    b = path.read_bytes(); n, f = (int(x) for x in np.frombuffer(b[8:16], np.uint32))
    return np.frombuffer(b[16:], np.float32).reshape(n, f)


SURF, st_, idx = S2 / "dashboard/surfels", a.pixel_setting, a.pixel
inp = rdbin(SURF / f"inputs_{st_}.bin")[idx]
k_cls = {1: "agree", 2: "conflict", 3: "unobserved"}[int(inp[7])]; region = "roof" if int(inp[8]) == 1 else "wall"
tau = 5.7 if st_[0] == "M" else 4.1; pn = PRIOR_NAME[st_[0]]
photo, prior = float(inp[12]) * 100, float(inp[13]) * 100                   # photo - GT, prior - GT (cm; + = above / outside)
res = {c: rdbin(SURF / f"surface_{st_}_{c}.bin")[idx] for c in SETTINGS[st_]}
view = json.loads((SURF / "views.json").read_text())[int(res[SETTINGS[st_][0]][10])]
target = photo if k_cls == "conflict" else prior                            # where the judgment sends the result
tab = {(r["condition"], r["region"], r["cls"]): r for r in csv.DictReader((S2 / "eval" / f"intent_{a.iteration}.csv").open())}
conds = SETTINGS[st_]
xs = {c: float(res[c][8]) * 100 for c in conds}                             # result - GT (cm)
fig = plt.figure(figsize=(15, 6.6))
ax = fig.add_axes([0.095, 0.13, 0.42, 0.74]); tx = fig.add_axes([0.55, 0.05, 0.44, 0.85]); tx.axis("off")
rows = {"in": 5.0, **{c: 3.6 - 0.8 * i for i, c in enumerate(conds)}}
vals = [photo, prior, 0.0, *xs.values()]
ax.set_xlim(max(vals) + 7, min(vals) - 7)                                   # outside / above on the left (camera side)
ax.set_ylim(rows[conds[-1]] - 0.7, 6.3)
band = "#ff9800" if k_cls == "conflict" else "#4285f4"
ax.axvspan(target - tau, target + tau, color=band, alpha=0.14, lw=0)
ax.text(target, 6.2, f"{'사진' if k_cls == 'conflict' else pn} ± τ\n= 판정대로 구간", ha="center", va="top", fontsize=9.5,
        color="#b35c00" if k_cls == "conflict" else "#1f4e9c")
ax.axvline(0, color="#111", lw=1.1, ls=(0, (4, 3)))
ax.text(0, rows["in"] + 0.72, "참값 ", ha="right", fontsize=9.5)
ax.plot([prior], [rows["in"]], "s", ms=13, color="#4285f4", zorder=3); ax.plot([photo], [rows["in"]], "o", ms=13, color="#ff9800", zorder=3)
ax.text(prior, rows["in"] + 0.3, f"{pn}  (② {abs(prior):.0f} cm)", ha="center", fontsize=10.5, color="#1f4e9c", weight="bold")
ax.text(photo, rows["in"] + 0.3, f"사진  (② {abs(photo):.0f} cm)", ha="center", fontsize=10.5, color="#b35c00", weight="bold")
ax.annotate("", xy=(photo, rows["in"] - 0.32), xytext=(prior, rows["in"] - 0.32), arrowprops=dict(arrowstyle="<->", color="#333", lw=1.1))
ax.text((prior + photo) / 2, rows["in"] - 0.62, f"① {abs(prior - photo):.0f} cm", ha="center", fontsize=10)
for c in conds:
    x = xs[c]; fol = abs(x - target) <= tau; col = "#2ea043" if fol else "#dc2626"
    ax.plot([0, x], [rows[c], rows[c]], color=col, lw=1, alpha=0.6)
    ax.plot([x], [rows[c]], "D", ms=11, color=col, zorder=3)
    ax.text(x, rows[c] + 0.22, f"④ {abs(x):.0f} cm", ha="center", fontsize=9, color=col)
ax.set_yticks([rows["in"], *(rows[c] for c in conds)])
ax.set_yticklabels(["입력", *(NAMES[c.split("_")[0]] for c in conds)], fontsize=10.5)
for sp in ("right", "top"):
    ax.spines[sp].set_visible(False)
ax.set_xlabel(("연직 높이" if region == "roof" else "벽 법선 방향") + " 거리 (cm, 참값 = 0; 왼쪽 = " + ("위" if region == "roof" else "바깥·카메라 쪽") + ")", fontsize=10)
ax.grid(axis="x", alpha=0.2)
T = tab[(conds[0], region, k_cls)]
todo = {"agree": "그 자리에 머물기", "conflict": "사진 자리로 가기", "unobserved": f"{pn} 자리에 머물기"}[k_cls]
fol_txt = ", ".join(f"{c.split('_')[0]} {'예' if abs(xs[c] - target) <= tau else '아니오'}" for c in conds)
err_txt = ", ".join(f"{c.split('_')[0]} {abs(xs[c]):.0f}" for c in conds)
lines = [("이 픽셀의 네 가지 비교", 13, "bold", "#111"),
         (f"① 칸 = 사진 ↔ {pn}:  |{pn} − 사진| = {abs(prior - photo):.0f} cm {'>' if abs(prior - photo) > tau else '≤'} τ {tau} cm", 11, "normal", "#111"),
         (f"     → {CLS_KO[k_cls]}, 시킨 것 = {todo}", 11, "normal", "#111"),
         (f"② 소스 오차 = 입력 ↔ 참값:  사진 {abs(photo):.0f} cm,  {pn} {abs(prior):.0f} cm", 11, "normal", "#111"),
         (f"③ 판정대로 = 결과가 시킨 자리(± τ) 안인가:  {fol_txt}", 11, "normal", "#111"),
         (f"④ 결과 오차 = 결과 ↔ 참값 (cm):  {err_txt}", 11, "normal", "#111"),
         ("", 8, "normal", "#111"),
         (f"표는 이런 픽셀을 칸별로 모은 것 — {'지붕' if region == 'roof' else '벽'} {CLS_KO[k_cls]} 칸 {int(T['n']):,}픽셀(15장):", 12, "bold", "#111"),
         (f"① 비율 {float(T['share']) * 100:.1f} % = 이 픽셀처럼 {CLS_KO[k_cls]}인 픽셀의 몫", 11, "normal", "#111"),
         (f"② 소스 오차 사진 {float(T['err_photos']) * 100:.0f} / {pn} {float(T['err_prior']) * 100:.0f} cm = ②값들의 중앙값" if T["err_photos"] not in ("", "nan")
          else f"② 소스 오차 {pn} {float(T['err_prior']) * 100:.0f} cm = ②값들의 중앙값", 11, "normal", "#111"),
         ("③ 판정대로 % = '예'의 몫:  " + ", ".join(f"{c.split('_')[0]} {float(tab[(c, region, k_cls)]['followed']) * 100:.0f} %" for c in conds), 11, "normal", "#111"),
         ("④ 결과 오차 = ④값들의 중앙값:  " + ", ".join(f"{c.split('_')[0]} {float(tab[(c, region, k_cls)]['err_result']) * 100:.0f} cm" for c in conds), 11, "normal", "#111"),
         ("", 8, "normal", "#111"),
         ("참값 = 정리한 참값(가려진 점 제거, 지면 기준 높이 맞춤). 참값이 있는 픽셀만 ②·④에 들어간다.", 9.5, "normal", "#666")]
y = 0.97
for t, fs, wt, col in lines:
    tx.text(0.0, y, t, fontsize=fs, weight=wt, color=col, va="top", transform=tx.transAxes); y -= 0.03 + fs * 0.0052
fig.suptitle(f"한 픽셀로 보는 표의 네 가지 비교 — 사진 {view[-6:-2]}, {'지붕' if region == 'roof' else '벽'} 픽셀 하나 (3D 보기 #pick={idx})",
             fontsize=13.5, x=0.01, ha="left", y=0.985)
fig.savefig(FIG / f"pixel_{st_}_{idx}.png", dpi=110); plt.close(fig)
print("pixel", idx, view, k_cls, region, dict(photo=photo, prior=prior, **{c: float(r[8]) * 100 for c, r in res.items()}))
print("done")
