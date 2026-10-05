"""Why each judgment class did or did not do what it was told: the two levers of the implementation read at every pixel of
the intent table (jointbuildgs:dev, CPU). scientific_verdict: null.

  python analyze_intent_mechanism.py [--iteration 30000] [--window 15]
Mounts: /s2 (payload; rw for eval/), /artifacts/JointBuildGS (ro).

ORDER_ko_v1 section 4 turns the judgment into two levers (jbgs_judgment.py):
  loss  : the photo term sum A|D-M| acts only where the photos measure (A=1); the prior term sum (1-A) rho_tau(D-P) only
          where they do not (A=0). rho_tau pulls with a constant slope between tau and 4 tau and exerts no force beyond
          4 tau ('do not insist on the prior').
  lock  : a prior-origin disk whose seeing training views mostly do not measure its spot (E < 0.5) is frozen
          (update x 0.01, opacity >= 0.5). E is a property of the SPOT over all 13 training views; the table class is a
          property of one PIXEL of one view.
For every pixel of the table (same pixels, classes and units as eval_intent.py) this script adds
  E_spot : E of the prior-surface point on that pixel's ray, computed exactly as compute_E (training views whose prior depth
           at the projection is within 0.5 m of the point's depth; mean A over them; 0 if none);
  ratio  : how far the prior is from the photo surface in tau: A=1 |M-P|/tau; A=0 |Mnb-P|/tau with Mnb = mean photo depth
           of the same face's measured pixels in a --window square around the pixel (the surface the neighbours pull to);
and reads, per setting x condition x region x class x E bin x ratio bin: pixel count, followed (as the table), at the
prior, at the photo (A=0: at Mnb), median |D-G|, |P-G|, |M-G| (A=0: |Mnb-G|), in cm (GT = JBGS_GT_SET, evaluation only).
Also counts the initial prior disks over each target roof face and near each target wall (disk density; M = LoD2 mesh sample,
L = ALS points), and, for the conflict wall pixels, the followed share against the distance to the nearest unmeasured (A=0)
pixel of the same face in the same view (--part extra; the window-neighbour check).
Outputs: eval/intent_mechanism_<it>.csv, eval/intent_mechanism_Eshare.csv, eval/intent_mechanism_density.csv,
eval/intent_mechanism_adjacency_<it>.csv, dashboard/reading/mechanism_summary.png (--part figures: from the csv only;
also fig_wall_halo.png, fig_view_dependent_roof.png, fig_check_matrix.png). --part cases draws the two cases of the
unmeasured region (photographed, depth mostly not measured: spot E < 0.5; LoD2 normal scene) as fig_case_wall.png (the
textureless wall between the windows, prior wrong) and fig_case_roof.png (the shaded roof face 3394, prior right), and
writes the numbers quoted with them to eval/intent_cases_<it>.csv (case_numbers).
The unmeasured pixels of the front wall are the textureless plaster between the windows, not the windows (checked on the
photos, 2026-09-29); the windows and frames are measured."""
import argparse
import csv
import json
import os
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d

GT_SET = os.environ.get("JBGS_GT_SET", "gt_clean")
S2 = Path("/s2"); MAPS = S2 / "inputs/maps"; ART = Path("/artifacts/JointBuildGS")
SPARSE = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions/B+1.0/scene/sparse_txt"
POLY = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json"
PHOTOS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images"
SETTINGS = {"M_N": ["P_M_N", "P0_M_N", "O_M_N", "I"], "M_B": ["P_M_B", "P0_M_B", "O_M_B", "I"],
            "L_N": ["P_L_N", "P0_L_N", "I"], "L_B": ["P_L_B", "P0_L_B", "I"]}
TAU_CM = {"M": 5.677, "L": 4.1}
CLS = {1: "agree", 2: "conflict", 3: "unobserved"}
RBINS = [(0.0, 1.0, "≤1τ"), (1.0, 2.0, "1–2τ"), (2.0, 4.0, "2–4τ"), (4.0, np.inf, ">4τ")]
ap = argparse.ArgumentParser()
ap.add_argument("--iteration", type=int, default=30000)
ap.add_argument("--window", type=int, default=15)
ap.add_argument("--depth-tol", type=float, default=0.5)
ap.add_argument("--part", default="all", choices=["all", "main", "extra", "figures", "cases"])
a = ap.parse_args()
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]
rec = json.loads((S2 / "eval/P_M_N" / f"render_{a.iteration}" / "receipt.json").read_text())["views"]
ALL = list(rec); TRAIN = [v for v, r in rec.items() if r["split"] == "train"]
W_, H_ = rec[ALL[0]]["size"]
calib = json.loads((S2 / "runs/P_M_N/scene/jbgs_calibration.json").read_text())["images"]


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


CAM = {}
for line in (SPARSE / "images.txt").read_text().splitlines():
    t = line.split()
    if len(t) >= 10 and not line.startswith("#") and t[9].lower().endswith(".jpg"):
        stem = Path(t[9]).stem
        if stem in calib:
            R = q2R([float(v) for v in t[1:5]]); tt = np.array([float(v) for v in t[5:8]])
            CAM[stem] = dict(R=R, t=tt, C=-R.T @ tt, K=np.array(calib[stem]["K"]))
cache = {}


def load(setname, view, dtype=np.float32):
    key = (setname, view)
    if key not in cache:
        p = MAPS / setname / "raw_depth" / f"{view}.npy"
        x = np.load(p if p.exists() else MAPS / setname / f"{view}.npy")
        cache[key] = cv2.resize(x.astype(np.float32), (W_, H_), interpolation=cv2.INTER_NEAREST).astype(dtype)
    return cache[key]


def rays(view):
    c = CAM[view]; K = c["K"]
    ys, xs = np.mgrid[0:H_, 0:W_]
    r = np.stack([(xs - K[0, 2]) / K[0, 0], (ys - K[1, 2]) / K[1, 1], np.ones(xs.shape)], -1)
    return r @ c["R"]                                                   # world direction per unit camera depth


def spot_E(X, prior):
    """compute_E for world points X [N,3] against the training views (nearest pixel, as the training code)."""
    ssum = np.zeros(len(X)); cnt = np.zeros(len(X))
    for u in TRAIN:
        c = CAM[u]; K = c["K"]
        Xc = X @ c["R"].T + c["t"]; z = Xc[:, 2]
        zz = np.where(z > 0.01, z, 1.0)
        ui = np.round(K[0, 0] * Xc[:, 0] / zz + K[0, 2]).astype(np.int64)
        vi = np.round(K[1, 1] * Xc[:, 1] / zz + K[1, 2]).astype(np.int64)
        ins = (z > 0.01) & (ui >= 0) & (ui < W_) & (vi >= 0) & (vi < H_)
        idx = np.clip(vi, 0, H_ - 1) * W_ + np.clip(ui, 0, W_ - 1)
        Pu, Au = load(prior, u).reshape(-1)[idx], load("conf", u).reshape(-1)[idx]
        sees = ins & np.isfinite(Pu) & (Pu > 0) & (np.abs(z - Pu) < a.depth_tol)
        ssum[sees] += Au[sees]; cnt[sees] += 1
    return np.where(cnt > 0, ssum / np.maximum(cnt, 1), 0.0), cnt


def med(x):
    return round(float(np.median(x)), 1) if x.size else None




def pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for fp in ("/fonts/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if Path(fp).exists():
            font_manager.fontManager.addfont(fp); plt.rcParams["font.family"] = font_manager.FontProperties(fname=fp).get_name(); break
    return plt


def figures():
    """Signature figure: conflict (share at the photo) and unobserved (share at the prior) for P, P0, I in every setting."""
    plt = pyplot()
    R = list(csv.DictReader((S2 / "eval" / f"intent_mechanism_{a.iteration}.csv").open()))
    get = lambda st, c, reg, k, eb="all", col="followed": next((float(r[col]) for r in R if r["setting"] == st and r["condition"] == c  # noqa: E731
                                                              and r["region"] == reg and r["cls"] == k and r["E_bin"] == eb and r["ratio_bin"] == "all"), np.nan)
    groups = [(st, reg) for st in SETTINGS for reg in ("roof", "wall")]
    lab = [f"{'LoD2' if st[0] == 'M' else 'ALS'}·{'정상' if st[2] == 'N' else '+1 m'}\n{'지붕' if reg == 'roof' else '벽'}" for st, reg in groups]
    cond = lambda st, m: next(c for c in SETTINGS[st] if c.split("_")[0] == m)  # noqa: E731
    fig, axes = plt.subplots(2, 1, figsize=(15, 9.2))
    x = np.arange(len(groups))
    spec = [("충돌 판정 — 판정 부합률(결과가 영상 깊이의 허용 폭 안).  기대 패턴: P ≈ I, P0 낮음", "conflict",
             [("P 판정 GS", "P", "all", "#2ea043"), ("I 영상 GS", "I", "all", "#8c8c8c"), ("P0 prior 강제 GS", "P0", "all", "#dc2626")]),
            ("미측정 판정 — 판정 부합률(결과가 prior 깊이의 허용 폭 안).  기대 패턴: P ≈ P0, I 낮음", "unobserved",
             [("P · 미관측 자리(관측 비율 < 0.5, 고정)", "P", "E<0.5", "#1b5e20"), ("P · 다른 영상이 잰 자리(관측 비율 ≥ 0.5)", "P", "E≥0.5", "#81c784"),
              ("P0 prior 강제 GS", "P0", "all", "#dc2626"), ("I 영상 GS", "I", "all", "#8c8c8c")])]
    for ax, (title, k, bars) in zip(axes, spec):
        w = 0.8 / len(bars)
        for i, (name, m, eb, col) in enumerate(bars):
            vals = [get(st, cond(st, m), reg, k, eb) * 100 for st, reg in groups]
            b = ax.bar(x - 0.4 + w * (i + 0.5), vals, w, color=col, label=name)
            for rect, v in zip(b, vals):
                if np.isfinite(v):
                    ax.text(rect.get_x() + rect.get_width() / 2, v + 1.2, f"{v:.0f}", ha="center", fontsize=7.5)
        ax.set_xticks(x); ax.set_xticklabels(lab, fontsize=9.5); ax.set_ylim(0, 112); ax.set_ylabel("%")
        ax.set_title(title, fontsize=12.5, loc="left"); ax.legend(fontsize=9, ncol=len(bars), loc="upper left", bbox_to_anchor=(0, 1.0), frameon=False)
        ax.grid(axis="y", alpha=0.25)
        for g in range(1, len(groups) // 2):
            ax.axvline(2 * g - 0.5, color="#ccc", lw=0.8)
    fig.tight_layout()
    out = S2 / "dashboard/reading"; out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "mechanism_summary.png", dpi=110); plt.close(fig)
    fig_wall_halo(plt, out); fig_view_dependent_roof(plt, out); fig_check_matrix(plt, out)
    print("figures written")


def fig_check_matrix(plt, out):
    """Appendix check: rows = intent x judgment x region, columns = settings; each cell shows P, P0, I as bars (judgment
    conformity; for faces no photo sees, the share of the prior face still covered) on a background that marks the
    author's reading of the expected pattern (green as expected, yellow partly, red opposite, grey not applicable).
    It checks whether P moved as the rule says, not whether the result is accurate."""
    R = list(csv.DictReader((S2 / "eval" / f"intent_mechanism_{a.iteration}.csv").open()))
    U = {(r["condition"], r["group"]): float(r["coverage"]) * 100 for r in csv.DictReader((S2 / "eval" / f"unseen_{a.iteration}.csv").open())}
    fol = lambda st, c, reg, k: next(float(r["followed"]) * 100 for r in R if r["setting"] == st and r["condition"] == c and r["region"] == reg  # noqa: E731
                                     and r["cls"] == k and r["E_bin"] == "all" and r["ratio_bin"] == "all")
    cond = lambda st, m: next(c for c in SETTINGS[st] if c.split("_")[0] == m)  # noqa: E731
    sts = list(SETTINGS)
    rows = [("유지 · 일치 판정 · 지붕", "기대: 셋 다 높음", "agree", "roof"), ("유지 · 일치 판정 · 벽", "기대: 셋 다 높음", "agree", "wall"),
            ("수정 · 충돌 판정 · 지붕", "기대: P ≈ I, P0 낮음", "conflict", "roof"), ("수정 · 충돌 판정 · 벽", "기대: P ≈ I, P0 낮음", "conflict", "wall"),
            ("유보 · 미측정 판정 · 지붕", "기대: P ≈ P0, I 낮음", "unobserved", "roof"), ("유보 · 미측정 판정 · 벽", "기대: P ≈ P0, I 낮음", "unobserved", "wall"),
            ("유보 · 비가시 면 · 뒷지붕", "기대: P만 높음 (남은 몫)", "unseen", "roof"), ("유보 · 비가시 면 · 뒷벽", "기대: P만 높음 (남은 몫)", "unseen", "wall")]
    # the author's reading of each cell (row, setting) -> (tint, note); default = as expected
    reading = {(1, "M_B"): None, (0, "M_B"): ("ok", "작은 판정 0.5 %"), (2, "L_N"): ("ok", "판정 효과 작음"),
               (3, "M_N"): ("ok", "벽면 둘레 번짐"), (3, "M_B"): ("ok", "벽면 둘레 번짐"), (3, "L_N"): ("ok", "벽면 둘레 번짐"), (3, "L_B"): ("ok", "벽면 둘레 번짐"),
               (4, "M_B"): ("ok", "틀린 +1 m 유지"), (4, "L_B"): ("no", "P가 I처럼 움직임"),
               (5, "M_N"): ("ok", "틀린 LoD2 유지"), (5, "M_B"): ("ok", "틀린 LoD2 유지"), (5, "L_N"): ("pt", "고정할 원반 없음"), (5, "L_B"): ("pt", "고정할 원반 없음"),
               (7, "L_N"): ("na", "ALS에 벽 없음"), (7, "L_B"): ("na", "ALS에 벽 없음")}
    tint = {"ok": "#e3f4e6", "pt": "#fff4d6", "no": "#fde2e1", "na": "#f0f0f0"}
    col = {"P": "#2ea043", "P0": "#dc2626", "I": "#8c8c8c"}
    fig = plt.figure(figsize=(16, 13.5))
    fig.text(0.01, 0.99, "판정별 점검 — 칸마다 P·P0·I의 판정 부합률(비가시 면은 prior가 남은 몫). 규칙대로 움직였는지를 보는 점검이며 결과의 정확도가 아니다",
             fontsize=14, va="top")
    fig.text(0.01, 0.966, "막대: 초록 P 판정 GS(제안) · 빨강 P0 prior 강제 GS · 회색 I 영상 GS.   배경: 초록 기대 패턴대로 · 노랑 부분 · 빨강 반대 · 회색 해당 없음",
             fontsize=11, va="top", color="#444")
    left, top, cw, rh = 0.2, 0.92, 0.195, 0.108
    for j, st in enumerate(sts):
        fig.text(left + j * cw + cw / 2, top + 0.008, f"{'LoD2' if st[0] == 'M' else 'ALS'} · {'정상' if st[2] == 'N' else '본지붕 +1 m'}", ha="center", fontsize=12)
    for i, (name, sub, k, reg) in enumerate(rows):
        y0 = top - (i + 1) * rh
        fig.text(0.01, y0 + rh * 0.62, name, fontsize=11.5, va="center")
        fig.text(0.01, y0 + rh * 0.35, sub, fontsize=10, va="center", color="#555")
        for j, st in enumerate(sts):
            if k == "unseen":
                vals = [U.get((cond(st, "P"), reg), np.nan), U.get((cond(st, "P0"), reg), np.nan), U.get(("I", reg), np.nan)]
            else:
                vals = [fol(st, cond(st, m), reg, k) for m in ("P", "P0", "I")]
            tn, note = reading.get((i, st)) or ("ok", "")
            ax = fig.add_axes([left + j * cw + 0.004, y0 + 0.006, cw - 0.008, rh - 0.012])
            ax.set_facecolor(tint[tn])
            yy = [2.2, 1.2, 0.2]
            for yv, v, m in zip(yy, vals, ("P", "P0", "I")):
                ax.barh(yv, v, height=0.62, color=col[m])
                ax.text(min(v, 100) + 1.5, yv, f"{v:.0f}", va="center", fontsize=9)
                ax.text(-2, yv, m, va="center", ha="right", fontsize=8.5, color="#555")
            ax.set_xlim(0, 118); ax.set_ylim(-0.6 if note else -0.3, 2.8)
            if note:
                ax.text(59, -0.45, note, ha="center", va="center", fontsize=9, color="#333")
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_color("#cfcfcf")
    fig.savefig(out / "fig_check_matrix.png", dpi=100); plt.close(fig)


def photo_gray(view):
    img = cv2.cvtColor(cv2.imread(str(next(PHOTOS.glob(f"{view}.*")))), cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (W_, H_), interpolation=cv2.INTER_AREA)
    return img, (cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)[..., None].repeat(3, -1) * 0.55).astype(np.float32)


def classes_of(view, setting):
    """Table classes of one view (1 agree, 2 conflict, 3 unobserved, 0 not a target pixel) and the inputs."""
    A, M, P, T = load("conf", view), load("mvs", view), load(f"prior_{setting}", view), load(f"tau_{setting[0]}", view)
    F = load("faceid", view, np.int32)
    hasM = np.isfinite(M) & (M > 0)
    base = np.isin(F, ROOF + WALL) & np.isfinite(P) & (P > 0) & np.isfinite(T)
    cls = np.zeros(F.shape, np.int8)
    cls[base & (A > 0) & hasM & (np.abs(M - P) <= T)] = 1
    cls[base & (A > 0) & hasM & (np.abs(M - P) > T)] = 2
    cls[base & (A <= 0)] = 3
    return cls, M, P, T, F


def tint(base, mask, rgb, w):
    base[mask] = (1 - w) * base[mask] + w * np.array(rgb, np.float32)


def fig_wall_halo(plt, out):
    """Conflict wall pixels next to unmeasured pixels (the textureless wall between the windows), P vs I, on the front wall
    of view 0009."""
    v, (x0, y0, x1, y1) = "DJI_20241217101313_0009_D", (480, 560, 1000, 860)
    img, gray = photo_gray(v)
    cls, M, P, T, F = classes_of(v, "M_N")
    wall = np.isin(F, WALL)
    c0 = gray.copy()
    tint(c0, wall & (cls == 2), (255, 152, 0), 0.45); tint(c0, wall & (cls == 3), (156, 39, 176), 0.75); tint(c0, wall & (cls == 1), (66, 133, 244), 0.6)
    panels = [("영상 0009 정면 벽 · 판정\n주황 충돌 · 보라 미측정(무늬 없는 벽면) · 파랑 일치", c0)]
    stats = {}
    for cond, name in (("P_M_N", "P 판정 GS"), ("I", "I 영상 GS")):
        D = np.load(S2 / "eval" / cond / f"render_{a.iteration}" / f"{v}_depth.npy")
        fol = np.abs(D - M) <= T
        c = gray.copy()
        c[wall & (cls == 2) & fol] = (46, 160, 67); c[wall & (cls == 2) & ~fol] = (220, 38, 38)
        tint(c, wall & (cls == 3), (156, 39, 176), 0.75)
        m = wall & (cls == 2)
        stats[cond] = float((m & fol).sum() / max(m.sum(), 1))
        panels.append((f"{name}: 충돌 픽셀의 판정 부합\n초록 부합(영상 깊이의 허용 폭 안) · 빨강 불부합 · 보라 무늬 없는 벽면(미측정)", c))
    adj = [r for r in csv.DictReader((S2 / "eval" / f"intent_mechanism_adjacency_{a.iteration}.csv").open()) if r["setting"] == "M_N"]
    fig = plt.figure(figsize=(15.5, 9.4))
    for i, (t, c) in enumerate(panels):
        ax = fig.add_axes([0.01 + (i % 2) * 0.5, 0.50 - (i // 2) * 0.47, 0.48, 0.39]); ax.imshow(c[y0:y1, x0:x1].astype(np.uint8)); ax.set_axis_off()
        ax.set_title(t, fontsize=11.5)
    ax = fig.add_axes([0.57, 0.07, 0.40, 0.36])
    bins = [r["dist_bin"] for r in adj if r["condition"] == "P_M_N"]
    xx = np.arange(len(bins)); w = 0.27
    for j, (cond, name, col) in enumerate((("P_M_N", "P 판정 GS", "#2ea043"), ("I", "I 영상 GS", "#8c8c8c"), ("P0_M_N", "P0 prior 강제 GS", "#dc2626"))):
        vals = [float(r["followed"]) * 100 for r in adj if r["condition"] == cond]
        b = ax.bar(xx + (j - 1) * w, vals, w, color=col, label=name)
        for rect, val in zip(b, vals):
            ax.text(rect.get_x() + rect.get_width() / 2, val + 1.5, f"{val:.0f}", ha="center", fontsize=8.5)
    share = [float(r["share"]) * 100 for r in adj if r["condition"] == "P_M_N"]
    ax.set_xticks(xx); ax.set_xticklabels([f"{b_}\n(충돌 픽셀의 {s_:.0f} %)" for b_, s_ in zip(bins, share)], fontsize=9.5)
    ax.set_ylim(0, 110); ax.set_ylabel("판정 부합률 (%)"); ax.grid(axis="y", alpha=0.25); ax.legend(fontsize=9, frameon=False, ncol=3, loc="upper left")
    ax.set_title("무늬 없는 벽면(같은 면의 미측정 픽셀)까지 거리별 판정 부합률 — 벽 충돌 픽셀, 15장 전체", fontsize=11.5)
    fig.suptitle(f"무늬 없는 벽면 둘레 번짐 (LoD2·정상). 이 영상의 벽 충돌 판정 부합률: P {stats['P_M_N'] * 100:.0f} %, I {stats['I'] * 100:.0f} %",
                 fontsize=13, x=0.01, ha="left", y=0.985)
    fig.savefig(out / "fig_wall_halo.png", dpi=100); plt.close(fig)


def fig_view_dependent_roof(plt, out):
    """The main roof in view 0031 (mostly unmeasured in this view) under the raised prior: LoD2 P vs ALS P vs I, the same
    LoD2 P model seen from above (view 0009), and per view the share of the main roof rendered at the raised prior."""
    v, (x0, y0, x1, y1) = "DJI_20241217101357_0031_D", (900, 300, 1600, 660)
    top = "DJI_20241217101313_0009_D"
    img, gray = photo_gray(v)
    cls, M, P, T, F = classes_of(v, "M_B")
    main = F == 3396
    tot = 0; two = 0                                                        # roof 'unobserved' pixels (LoD2 +1 m) on the main roof of 0031 / 0032
    for u in ALL:
        cu, _, _, _, Fu = classes_of(u, "M_B")
        un_u = (cu == 3) & np.isin(Fu, ROOF); tot += int(un_u.sum())
        if u.endswith(("0031_D", "0032_D")):
            two += int((un_u & (Fu == 3396)).sum())

    def raised_map(view, cond, setting, gray_v, main_v, outline=None):
        D = np.load(S2 / "eval" / cond / f"render_{a.iteration}" / f"{view}_depth.npy")
        Pr, Tr, FVv = load(f"prior_{setting}", view), load(f"tau_{setting[0]}", view), load("fvert", view)
        at = np.abs(D - Pr) <= Tr; low = (Pr - D) * FVv <= -0.8
        c = gray_v.copy()
        c[main_v & at] = (220, 38, 38); c[main_v & low] = (46, 160, 67); c[main_v & ~at & ~low & (D > 0)] = (250, 204, 21)
        if outline is not None:
            c[cv2.morphologyEx(outline.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0] = (255, 255, 255)
        return c, at

    un = main & (cls == 3)
    c0 = gray.copy()
    tint(c0, un, (156, 39, 176), 0.7); tint(c0, main & (cls == 2), (255, 152, 0), 0.45)
    panels = [(f"영상 0031 본지붕 · 판정 (LoD2 +1 m)\n보라 미측정 = 본지붕의 {un.sum() / max(main.sum(), 1) * 100:.0f} % · 주황 충돌", c0, (x0, y0, x1, y1))]
    for cond, setting, name in (("P_M_B", "M_B", "LoD2 +1 m · P"), ("P_L_B", "L_B", "ALS +1 m · P"), ("I", "M_B", "I 영상 GS (참고)")):
        c, at = raised_map(v, cond, setting, gray, main, un)
        panels.append((f"{name} · 영상 0031\n미측정 구역의 {(un & at).sum() / max(un.sum(), 1) * 100:.0f} %가 +1 m에 남음 (흰 선 = 미측정 구역)", c, (x0, y0, x1, y1)))
    _, gray_t = photo_gray(top)
    Ft = load("faceid", top, np.int32); main_t = Ft == 3396
    ys, xs = np.nonzero(main_t)
    ct, at_t = raised_map(top, "P_M_B", "M_B", gray_t, main_t)
    panels.insert(4, (f"LoD2 +1 m · P · 같은 본지붕을 위에서 찍은 영상 0009\n+1 m에 남은 픽셀 {(main_t & at_t).sum() / max(main_t.sum(), 1) * 100:.0f} %",
                      ct, (max(xs.min() - 20, 0), max(ys.min() - 20, 0), min(xs.max() + 20, W_), min(ys.max() + 20, H_))))
    views = ["0005", "0009", "0024", "0031", "0032"]
    share = {c: [] for c in ("P_M_B", "P_L_B")}; a0 = []
    for tail in views:
        u = next(x for x in ALL if x.endswith(f"_{tail}_D"))
        Fu = load("faceid", u, np.int32); mu = Fu == 3396; Au = load("conf", u)
        a0.append((mu & (Au <= 0)).sum() / max(mu.sum(), 1) * 100)
        for cond, setting in (("P_M_B", "M_B"), ("P_L_B", "L_B")):
            D = np.load(S2 / "eval" / cond / f"render_{a.iteration}" / f"{u}_depth.npy")
            Pr, Tr = load(f"prior_{setting}", u), load(f"tau_{setting[0]}", u)
            share[cond].append(((mu & (np.abs(D - Pr) <= Tr)).sum()) / max(mu.sum(), 1) * 100)
    fig = plt.figure(figsize=(20, 10.4))
    for i, (t, c, (cx0, cy0, cx1, cy1)) in enumerate(panels):
        ax = fig.add_axes([0.005 + (i % 3) * 0.333, 0.50 - (i // 3) * 0.47, 0.32, 0.38]); ax.imshow(c[cy0:cy1, cx0:cx1].astype(np.uint8)); ax.set_axis_off()
        ax.set_title(t, fontsize=11)
    ax = fig.add_axes([0.705, 0.08, 0.27, 0.32])
    xx = np.arange(len(views)); w = 0.36
    for j, (cond, name, col) in enumerate((("P_M_B", "LoD2 +1 m · P", "#dc2626"), ("P_L_B", "ALS +1 m · P", "#f59e0b"))):
        b = ax.bar(xx + (j - 0.5) * w, share[cond], w, color=col, label=name)
        for rect, val in zip(b, share[cond]):
            ax.text(rect.get_x() + rect.get_width() / 2, val + 1.2, f"{val:.0f}", ha="center", fontsize=8.5)
    ax.plot(xx, a0, "o--", color="#9c27b0", label="그 영상의 본지붕 중 미측정(%)")
    ax.set_xticks(xx); ax.set_xticklabels([f"영상 {t}" for t in views], fontsize=9.5); ax.set_ylim(0, 80)
    ax.set_ylabel("본지붕 중 +1 m에 남은 몫 (%)"); ax.grid(axis="y", alpha=0.25); ax.legend(fontsize=8.5, frameon=False, loc="upper left")
    ax.set_title("영상별: 본지붕이 +1 m로 렌더된 몫", fontsize=11)
    fig.text(0.01, 0.985, f"영상마다 다른 지붕 — 본지붕 +1 m 주입. 지붕 미측정 픽셀의 {two / max(tot, 1) * 100:.0f} %가 비스듬한 두 영상(0031·0032)의 본지붕이다. "
             "빨강 = 올린 prior(+1 m)에 남음 · 초록 = 실제 지붕 · 노랑 = 그 사이", fontsize=12.5, va="top")
    fig.savefig(out / "fig_view_dependent_roof.png", dpi=95); plt.close(fig)


def fig_cases():
    """Two cases of the unmeasured region, LoD2 normal scene: photo, the spots most seeing views do not measure (E < 0.5,
    purple), and |D - GT| of P and I there (GT pixels only; 1-px gaps between GT samples filled for legibility)."""
    plt = pyplot()
    out = S2 / "dashboard/reading"; out.mkdir(parents=True, exist_ok=True)
    cmap = plt.get_cmap("RdYlGn_r")
    cases = [("DJI_20241217101321_0013_D", WALL, "wall", "정면 벽 (영상 0013)", False,
              "무늬 없는 벽면(창 사이의 노란 회벽): LoD2는 약 22 cm 바깥(틀림). 같은 벽의 창·창틀·장식은 영상이 재서 '충돌' → 판정 GS도 실제 벽으로 옮김"),
             ("DJI_20241217101305_0005_D", ROOF, "roof", "그늘진 지붕면 3394 (영상 0005)", True,
              "그늘진 지붕면(3394)과 그 위쪽 가장자리: LoD2는 맞음(참값에서 약 4.5 cm). 이 면의 잰 부분은 일치·충돌이 반씩 갈림")]
    for v, reg_faces, tag, title, main_blob, sub in cases:
        A, P, T = load("conf", v), load("prior_M_N", v), load("tau_M", v)
        FV, F, G = load("fvert", v), load("faceid", v, np.int32), load(GT_SET, v)
        base = np.isin(F, reg_faces) & np.isfinite(P) & (P > 0) & np.isfinite(T)
        ys, xs = np.nonzero(base & (A <= 0))
        E, _ = spot_E(CAM[v]["C"] + rays(v)[ys, xs] * P[ys, xs, None], "prior_M_N")
        mk = np.zeros(F.shape, bool); mk[ys[E < 0.5], xs[E < 0.5]] = True
        yy, xx = np.nonzero(mk)
        (ylo, yhi), (xlo, xhi) = np.percentile(yy, [2, 98]), np.percentile(xx, [2, 98])
        pad = 70
        if main_blob:                                                       # crop to the largest blob (a few stray spots elsewhere)
            n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(mk.astype(np.uint8), np.ones((25, 25), np.uint8)))
            k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            xlo, ylo = st[k, cv2.CC_STAT_LEFT], st[k, cv2.CC_STAT_TOP]
            xhi, yhi = xlo + st[k, cv2.CC_STAT_WIDTH], ylo + st[k, cv2.CC_STAT_HEIGHT]
            pad = 40
        y0, y1, x0, x1 = int(max(ylo - pad, 0)), int(min(yhi + pad, H_)), int(max(xlo - pad, 0)), int(min(xhi + pad, W_))
        img, gray = photo_gray(v)
        ov = img.astype(np.float32); tint(ov, mk, (160, 50, 210), 0.6)
        hasG = mk & np.isfinite(G) & (G > 0)
        fig, axes = plt.subplots(2, 2, figsize=(17, 17 * (y1 - y0) / (x1 - x0) + 1.6), gridspec_kw=dict(wspace=0.02, hspace=0.12))
        axes[0, 0].imshow(img[y0:y1, x0:x1]); axes[0, 0].set_title(f"{title} — 사진", fontsize=15)
        axes[0, 1].imshow(ov[y0:y1, x0:x1].astype(np.uint8)); axes[0, 1].set_title("보라 = 대부분의 영상이 깊이를 못 잰 자리 (사진에는 찍혀 있음)", fontsize=15)
        for ci, (cond, nm) in enumerate((("P_M_N", "판정 GS"), ("I", "영상 GS"))):
            err = np.abs(np.load(S2 / "eval" / cond / f"render_{a.iteration}" / f"{v}_depth.npy") - G) * FV * 100
            pic = gray.copy()
            pic[hasG] = (np.array(cmap(np.clip(err[hasG] / 30.0, 0, 1)))[:, :3] * 255).astype(np.float32)
            gap = cv2.dilate(hasG.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & ~hasG & mk
            src = cv2.dilate(np.where(hasG, err, 0).astype(np.float32), np.ones((3, 3), np.uint8))
            pic[gap] = (np.array(cmap(np.clip(src[gap] / 30.0, 0, 1)))[:, :3] * 255).astype(np.float32)
            axes[1, ci].imshow(pic[y0:y1, x0:x1].astype(np.uint8))
            axes[1, ci].set_title(f"{nm}: 보라 자리가 참값에서 떨어진 거리 (중앙 {np.median(err[hasG]):.0f} cm)", fontsize=15)
        for ax in axes.ravel():
            ax.set_xticks([]); ax.set_yticks([])
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 30)); sm.set_array([])
        fig.colorbar(sm, ax=axes[1, :].tolist(), fraction=0.025, pad=0.01, aspect=12).set_label("cm (30 이상은 같은 색)", fontsize=12)
        fig.suptitle(sub, fontsize=15, x=0.01, ha="left", y=0.995)
        fig.savefig(out / f"fig_case_{tag}.png", dpi=90, bbox_inches="tight"); plt.close(fig)
        print("case", tag, flush=True)


def case_numbers():
    """Numbers quoted with the cases, LoD2: photo texture (7 x 7 grey-level std) and brightness of the unmeasured spots
    (E < 0.5) per region against the measured roof pixels; P, P0, I |D - GT| on the unmeasured roof spots by distance to the
    face boundary in the image (normal scene); per face the agree / conflict / unmeasured shares (normal and injected scene).
    Output: eval/intent_cases_<it>.csv."""
    conds = ("P_M_N", "P0_M_N", "I")
    acc = {k: [] for k in ("roof", "E", "dist", "tex", "gray", "G", "FV")}
    D = {c: [] for c in conds}
    mtex, mgray = [], []
    comp = {(st, f): np.zeros(3, np.int64) for st in ("M_N", "M_B") for f in (3394, 3396, 3403)}
    for v in ALL:
        A, M, P, T = load("conf", v), load("mvs", v), load("prior_M_N", v), load("tau_M", v)
        FV, F, G = load("fvert", v), load("faceid", v, np.int32), load(GT_SET, v)
        hasM = np.isfinite(M) & (M > 0)
        g = cv2.resize(cv2.imread(str(next(PHOTOS.glob(f"{v}.*"))), cv2.IMREAD_GRAYSCALE), (W_, H_), interpolation=cv2.INTER_AREA).astype(np.float32)
        mu = cv2.blur(g, (7, 7)); tex = np.sqrt(np.maximum(cv2.blur(g * g, (7, 7)) - mu * mu, 0))
        for st in ("M_N", "M_B"):
            Ps = load(f"prior_{st}", v)
            bs = np.isin(F, ROOF + WALL) & np.isfinite(Ps) & (Ps > 0) & np.isfinite(T)
            for f in (3394, 3396, 3403):
                m = bs & (F == f)
                comp[(st, f)] += [int((m & (A > 0) & hasM & (np.abs(M - Ps) <= T)).sum()), int((m & (A > 0) & hasM & (np.abs(M - Ps) > T)).sum()),
                                  int((m & (A <= 0)).sum())]
        base = np.isin(F, ROOF + WALL) & np.isfinite(P) & (P > 0) & np.isfinite(T)
        mr = base & np.isin(F, ROOF) & (A > 0) & hasM
        mtex.append(tex[mr]); mgray.append(g[mr])
        ys, xs = np.nonzero(base & (A <= 0))
        E, _ = spot_E(CAM[v]["C"] + rays(v)[ys, xs] * P[ys, xs, None], "prior_M_N")
        dist = np.zeros(F.shape, np.float32)                               # px to the face's own boundary in this view
        for f in np.unique(F[ys, xs]):
            inf = F == f
            dist[inf] = cv2.distanceTransform(inf.astype(np.uint8), cv2.DIST_L2, 3)[inf]
        for k, x in (("roof", np.isin(F[ys, xs], ROOF)), ("E", E), ("dist", dist[ys, xs]), ("tex", tex[ys, xs]), ("gray", g[ys, xs]),
                     ("G", G[ys, xs]), ("FV", FV[ys, xs])):
            acc[k].append(x)
        for c in conds:
            D[c].append(np.load(S2 / "eval" / c / f"render_{a.iteration}" / f"{v}_depth.npy")[ys, xs])
        print("cases", v, flush=True)
    r = {k: np.concatenate(x) for k, x in acc.items()}; d = {c: np.concatenate(x) for c, x in D.items()}
    rows = [dict(kind="photo_texture", setting="M_N", region="roof", subset="measured", n=int(sum(x.size for x in mtex)),
                 texture_std=med(np.concatenate(mtex)), gray=med(np.concatenate(mgray)))]
    for reg in ("roof", "wall"):
        sel = (r["roof"] == (reg == "roof")) & (r["E"] < 0.5)
        rows.append(dict(kind="photo_texture", setting="M_N", region=reg, subset="unmeasured E<0.5", n=int(sel.sum()),
                         texture_std=med(r["tex"][sel]), gray=med(r["gray"][sel])))
    ok = r["roof"] & (r["E"] < 0.5) & np.isfinite(r["G"]) & (r["G"] > 0)
    for lo, hi, nm in ((0, 3, "<=3 px"), (3, 10, "3-10 px"), (10, 1e9, ">10 px"), (0, 1e9, "all")):
        m = ok & (r["dist"] > lo) & (r["dist"] <= hi) if lo > 0 else ok & (r["dist"] <= hi)
        rows.append(dict(kind="roof_unmeasured_by_edge_distance", setting="M_N", region="roof", subset=nm, n=int(m.sum()),
                         **{f"err_{c}_cm": med(np.abs(d[c][m] - r["G"][m]) * r["FV"][m] * 100) for c in conds}))
    for (st, f), (ag, co, un) in comp.items():
        rows.append(dict(kind="face_judgment_mix", setting=st, region=str(f), subset="all views", n=int(ag + co + un),
                         agree_of_measured=round(ag / max(ag + co, 1), 4), conflict_of_measured=round(co / max(ag + co, 1), 4),
                         unmeasured_share=round(un / max(ag + co + un, 1), 4)))
    keys = []
    for row in rows:
        keys += [k for k in row if k not in keys]
    with (S2 / "eval" / f"intent_cases_{a.iteration}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
    for row in rows:
        print(row, flush=True)


if a.part == "figures":
    figures(); raise SystemExit(0)
if a.part == "cases":
    fig_cases(); case_numbers(); raise SystemExit(0)

rows, eshare = [], []
for setting, conds in (SETTINGS.items() if a.part in ("all", "main") else []):
    prior, tau = f"prior_{setting}", f"tau_{setting[0]}"
    pix = {}
    for v in ALL:                                                          # inputs, identical for every condition
        A, M, P, T = load("conf", v), load("mvs", v), load(prior, v), load(tau, v)
        FV, F, G = load("fvert", v), load("faceid", v, np.int32), load(GT_SET, v)
        hasM = np.isfinite(M) & (M > 0)
        base = np.isin(F, ROOF + WALL) & np.isfinite(P) & (P > 0) & np.isfinite(T)
        cls = np.zeros(F.shape, np.int8)
        cls[base & (A > 0) & hasM & (np.abs(M - P) <= T)] = 1
        cls[base & (A > 0) & hasM & (np.abs(M - P) > T)] = 2
        cls[base & (A <= 0)] = 3
        Mnb = np.full(F.shape, np.nan, np.float32)                         # neighbours' photo surface, same face only
        for f in ROOF + WALL:
            inf = F == f
            if not (inf & (cls == 3)).any():
                continue
            mf = (inf & (A > 0) & hasM).astype(np.float32)
            num = cv2.boxFilter(np.where(mf > 0, M, 0).astype(np.float32), -1, (a.window, a.window), normalize=False)
            den = cv2.boxFilter(mf, -1, (a.window, a.window), normalize=False)
            ok = inf & (den >= 5)
            Mnb[ok] = num[ok] / den[ok]
        ys, xs = np.nonzero(cls > 0)
        X = CAM[v]["C"] + rays(v)[ys, xs] * P[ys, xs, None]
        E, cnt = spot_E(X, prior)
        c = cls[ys, xs]
        ref = np.where(c == 3, Mnb[ys, xs], M[ys, xs])
        pix[v] = dict(ys=ys, xs=xs, cls=c, roof=np.isin(F[ys, xs], ROOF), E=E.astype(np.float32), cnt=cnt.astype(np.int16),
                      ratio=(np.abs(ref - P[ys, xs]) / T[ys, xs]).astype(np.float32), P=P[ys, xs], M=M[ys, xs], ref=ref,
                      T=T[ys, xs], FV=FV[ys, xs], G=G[ys, xs])
        print(setting, v, "pixels", len(ys), flush=True)
    # share of each class in each E bin (input property; the same for every condition)
    for region in ("roof", "wall"):
        for k, name in CLS.items():
            E = np.concatenate([p["E"][(p["cls"] == k) & (p["roof"] == (region == "roof"))] for p in pix.values()])
            eshare.append(dict(setting=setting, region=region, cls=name, n=int(E.size), share_E_lt_05=round(float((E < 0.5).mean()), 4) if E.size else None,
                               E_mean=round(float(E.mean()), 3) if E.size else None))
    for cond in conds:
        rdir = S2 / "eval" / cond / f"render_{a.iteration}"
        cols = {k: [] for k in ("roof", "cls", "eb", "rb", "fol", "atP", "atR", "hasG", "er", "ep", "ef")}
        for v, p in pix.items():                                            # per pixel: codes and outcomes, then group once
            D = np.load(rdir / f"{v}_depth.npy")[p["ys"], p["xs"]]
            ok = D > 0
            atP = np.abs(D - p["P"]) <= p["T"]
            atR = np.isfinite(p["ref"]) & (np.abs(D - p["ref"]) <= p["T"])
            rb = np.full(len(D), len(RBINS), np.int8)                       # code len(RBINS) = no neighbour photo
            for i, (lo, hi, _) in enumerate(RBINS):
                rb[np.isfinite(p["ratio"]) & (p["ratio"] > lo if lo > 0 else p["ratio"] >= 0) & (p["ratio"] <= hi)] = i
            for k, x in (("roof", p["roof"]), ("cls", p["cls"]), ("eb", (p["E"] >= 0.5).astype(np.int8)), ("rb", rb),
                         ("fol", np.where(p["cls"] == 2, atR, atP)), ("atP", atP), ("atR", atR),
                         ("hasG", np.isfinite(p["G"]) & (p["G"] > 0)), ("er", np.abs(D - p["G"]) * p["FV"] * 100),
                         ("ep", np.abs(p["P"] - p["G"]) * p["FV"] * 100), ("ef", np.abs(p["ref"] - p["G"]) * p["FV"] * 100)):
                cols[k].append(x[ok])
        c = {k: np.concatenate(x) for k, x in cols.items()}
        rbname = [x[2] for x in RBINS] + ["none"]
        for region in ("roof", "wall"):
            for k, name in CLS.items():
                base = (c["roof"] == (region == "roof")) & (c["cls"] == k)
                tot = int(base.sum())
                for eb in ("E<0.5", "E≥0.5", "all"):
                    for ri in list(range(len(rbname))) + ["all"]:
                        m = base.copy()
                        if eb != "all":
                            m &= c["eb"] == (1 if eb == "E≥0.5" else 0)
                        if ri != "all":
                            m &= c["rb"] == ri
                        n = int(m.sum())
                        if n == 0:
                            continue
                        g = m & c["hasG"]
                        rows.append(dict(iteration=a.iteration, setting=setting, condition=cond, region=region, cls=name, E_bin=eb,
                                         ratio_bin=rbname[ri] if ri != "all" else "all", n=n, share_of_class=round(n / max(tot, 1), 4),
                                         followed=round(float(c["fol"][m].mean()), 4), at_prior=round(float(c["atP"][m].mean()), 4),
                                         at_photo=round(float(c["atR"][m].mean()), 4), err_result_cm=med(c["er"][g]),
                                         err_prior_cm=med(c["ep"][g]), err_photo_cm=med(c["ef"][g & np.isfinite(c["ef"])]), n_gt=int(g.sum())))
        print(setting, cond, "done", flush=True)
    cache.clear()

if rows:
    with (S2 / "eval" / f"intent_mechanism_{a.iteration}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with (S2 / "eval" / "intent_mechanism_Eshare.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(eshare[0])); w.writeheader(); w.writerows(eshare)
if a.part == "main":
    raise SystemExit(0)

# initial prior disk density over the target roof faces (lock resolution): M = LoD2 mesh sample, L = ALS points
PJ = {int(p["poly_index"]): p for p in json.loads(POLY.read_text())["polygons"]}
dens = []
for cond in ("P_M_N", "P_L_N", "P_M_B", "P_L_B"):
    sp = S2 / "runs" / cond / "scene/sparse/0"
    xyz = np.asarray(o3d.io.read_point_cloud(str(sp / "points3D.ply")).points)
    org = np.load(sp / "origin.npy")
    pr = xyz[org == 1]
    for f in ROOF:
        ring = np.array(json.loads(PJ[f]["ring_local_xy"]) if isinstance(PJ[f]["ring_local_xy"], str) else PJ[f]["ring_local_xy"], np.float32)
        inside = np.array([cv2.pointPolygonTest(ring.reshape(-1, 1, 2), (float(x), float(y)), False) >= 0 for x, y in pr[:, :2]])
        z0 = float(PJ[f]["z_local_mean"])
        on = inside & (pr[:, 2] > z0 - 3.0)                                 # roof points, not the ground below eaves
        area = float(PJ[f]["area_m2"])
        dens.append(dict(condition=cond, face=f, area_m2=round(area, 1), prior_disks=int(on.sum()), per_m2=round(on.sum() / area, 2)))
    for f in WALL:                                                          # disks within 0.3 m of the wall line, above ground
        rr = PJ[f]["ring_local_xy"]
        ring = np.array(json.loads(rr) if isinstance(rr, str) else rr, np.float64)
        e = np.unique(ring.round(3), axis=0)
        if len(e) < 2:
            continue
        p0, p1 = e[0], e[-1]; d = p1 - p0; L = np.linalg.norm(d)
        t = np.clip(((pr[:, :2] - p0) @ d) / (L * L), 0, 1)
        near = np.linalg.norm(pr[:, :2] - (p0 + t[:, None] * d), axis=1) < 0.3
        area = float(PJ[f]["area_m2"])
        dens.append(dict(condition=cond, face=f, area_m2=round(area, 1), prior_disks=int(near.sum()), per_m2=round(near.sum() / area, 2)))
    print("density", cond, flush=True)
with (S2 / "eval" / "intent_mechanism_density.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(dens[0])); w.writeheader(); w.writerows(dens)

# window-neighbour check: conflict wall pixels, followed vs distance (px) to the nearest A=0 pixel of the same face
adj = []
DBINS = [(0, 2, "≤2 px"), (2, 5, "3–5 px"), (5, 10, "6–10 px"), (10, 1e9, ">10 px")]
for setting, conds in SETTINGS.items():
    prior, tau = f"prior_{setting}", f"tau_{setting[0]}"
    for cond in conds:
        rdir = S2 / "eval" / cond / f"render_{a.iteration}"
        acc = {nm: [0, 0] for *_, nm in DBINS}
        for v in ALL:
            A, M, P, T, F = load("conf", v), load("mvs", v), load(prior, v), load(tau, v), load("faceid", v, np.int32)
            D = np.load(rdir / f"{v}_depth.npy")
            hasM = np.isfinite(M) & (M > 0)
            base = np.isfinite(P) & (P > 0) & np.isfinite(T) & (D > 0)
            conf = base & np.isin(F, WALL) & (A > 0) & hasM & (np.abs(M - P) > T)
            dist = np.full(F.shape, np.inf, np.float32)
            for f in WALL:
                inf = F == f
                if not (conf & inf).any():
                    continue
                un = (inf & (A <= 0) & np.isfinite(P)).astype(np.uint8)
                if not un.any():
                    continue
                dt = cv2.distanceTransform(1 - un, cv2.DIST_L2, 3)
                dist[inf] = dt[inf]
            fol = np.abs(D - M) <= T
            for lo, hi, nm in DBINS:
                m = conf & (dist > lo) & (dist <= hi) if lo > 0 else conf & (dist <= hi)
                acc[nm][0] += int(m.sum()); acc[nm][1] += int((m & fol).sum())
        tot = sum(x[0] for x in acc.values())
        for nm, (n, k) in acc.items():
            adj.append(dict(iteration=a.iteration, setting=setting, condition=cond, dist_bin=nm, n=n, share=round(n / max(tot, 1), 4),
                            followed=round(k / max(n, 1), 4)))
        print("adjacency", setting, cond, flush=True)
    cache.clear()
with (S2 / "eval" / f"intent_mechanism_adjacency_{a.iteration}.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(adj[0])); w.writeheader(); w.writerows(adj)
figures()
print("done")
