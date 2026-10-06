"""PHD-MAIN-PREP-MEASURE-v1 step 07 (jointbuildgs:dev, CPU): representative figure rows.

  python step07_rows.py <spec_json_relative_to_/out> [--out-sub figrows]

Row = [photo crop | observation confidence (c) | agree / conflict marks | unit state and judgment | section], all in the
row's view: spec "view" (step 07a; v1.1 nadir for roof items), or else the most nadir training view holding the centre.
The per-view panels are re-rendered for the chosen view with the registered prior of the row's range (same rules as step 03);
the section samples the registered prior (vertical rays), the current MVS (survey v1 DSM, 0.5 m) and the GT (cleaned ULS,
step 04; B0: gt_clean) along A -> B. spec: {"rows": [{"tid", "range", "prior", "centre": [x, y] local, "half_m", "line": [[x, y], [x, y]],
"view" (optional), "title", "note"}]}. scientific_verdict: null."""
import argparse
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
import numpy as np

from common import CFG, DENSE, OUT, SURVEY, GRID_H, GRID_W, Scene, Views, read_depth_bin
from src.phd.prior_propagation_v4 import conversion as conv
from src.phd.prior_propagation_v4 import locations as locs
from src.phd.prior_propagation_v4 import rule
import step03_stage1 as s3

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("spec"); ap.add_argument("--out-sub", default="figrows")
    ap.add_argument("--stage1-sub", default="step03"); ap.add_argument("--gt-sub", default="step04"); ap.add_argument("--mesh-sub", default="step02")
    a = ap.parse_args()
    spec = json.loads((OUT / a.spec).read_text())
    O = OUT / a.out_sub; O.mkdir(parents=True, exist_ok=True)
    V = Views()
    Sv = dict(np.load(SURVEY / "derived.npz"))
    cache = {}
    for row in spec["rows"]:
        rid, prior = row["range"], row["prior"]
        key = (rid, prior, row.get("stage1_sub", a.stage1_sub))
        if key not in cache:
            S1 = OUT / key[2] / rid / prior
            summ = json.loads((S1 / "summary.json").read_text())
            pr = s3.Prior(OUT / row.get("mesh_sub", a.mesh_sub) / rid, prior)
            pr.shift = np.asarray(summ["registration"]["shift_applied"], float)
            sc, _ = pr.scene()
            U = locs.load_store(S1 / "units.npz")
            gtp = np.load(OUT / row.get("gt_sub", a.gt_sub) / rid / "gt_primary.npz")["xyz"]
            pairs = np.load(S1 / "unit_view_pairs.npz")
            cache[key] = dict(summ=summ, pr=pr, sc=sc, U=U, gtp=gtp, views=[str(v) for v in pairs["views"]],
                              mvs=Path(row.get("mvs_dir", str(DENSE))))
        c = cache[key]; pr, sc, U, summ = c["pr"], c["sc"], c["U"], c["summ"]
        tau = {1: summ["tolerance"]["roof"]["tau"], 2: summ["tolerance"]["wall"]["tau"]}
        cx, cy = row["centre"]
        zc = float(row.get("z", np.nan))
        # view: the most nadir training view whose image holds the centre (prior height there)
        if not np.isfinite(zc):
            t, tri = sc.cast_points(np.array([[cx, cy, 250.0]]), np.array([[0, 0, -1.0]]))
            zc = 250.0 - float(t[0]) if np.isfinite(t[0]) else -40.0
        Xc = np.array([[cx, cy, zc]])
        best = row.get("view")
        if best:
            u_, v_, z_ = V.project(best, Xc)
            if not (z_[0] > 0 and 60 <= u_[0] < GRID_W - 60 and 60 <= v_[0] < GRID_H - 60):
                best = None
        if not best:
            cand = []
            for n in c["views"]:
                u, v, z = V.project(n, Xc)
                if z[0] > 0 and 60 <= u[0] < GRID_W - 60 and 60 <= v[0] < GRID_H - 60:
                    cand.append((V.tilt(n), n))
            best = sorted(cand)[0][1] if cand else c["views"][0]
        n = best
        Dr = V.rays(n); C = V.C(n)
        tP, tri = sc.cast(C, Dr)
        dm = read_depth_bin(c["mvs"] / "stereo/depth_maps" / f"{n}.geometric.bin")
        a1 = np.isfinite(dm) & (dm > 0)
        hit = tri >= 0
        nn = np.zeros((GRID_H, GRID_W, 3)); nn[hit] = pr.n_used[tri[hit]]
        f = conv.factor(nn, Dr.astype(np.float64), has_surface=hit)
        bf = np.zeros_like(hit); bf[hit] = pr.bface_tri[tri[hit]]
        kind = conv.surface_kind(nn[..., 2])
        tp = np.where(bf, np.where(kind == 1, tau[1], tau[2]), tau[1])
        r = (dm - tP) * f
        mark = np.full((GRID_H, GRID_W), -1, np.int8)
        mark[hit & a1 & (np.abs(r) <= tp)] = 0; mark[hit & a1 & ~(np.abs(r) <= tp)] = 1
        ci = np.full(tri.shape, -1, np.int64); ci[hit] = pr.ci_of_tri[tri[hit]]
        X = C[None, None, :] + tP[..., None] * Dr.astype(np.float64)
        loc = np.full(tri.shape, -1, np.int64)
        okl = ci >= 0
        loc[okl] = locs.locate(U, ci[okl], X[okl])
        stp = np.full(tri.shape, -1, np.int8)                  # unit display class
        st, vo, J = U["state"], U["vote"], U["J"]
        lv = loc[okl]
        cls = np.full(len(lv), 0, np.int8)
        cls[(st[lv] == rule.ST_SUPPORT) & (vo[lv] == rule.V_AGREE)] = 1
        cls[(st[lv] == rule.ST_SUPPORT) & (vo[lv] == rule.V_CONFLICT)] = 2
        cls[(st[lv] == rule.ST_MISSING) & (J[lv] == rule.J_AGREE)] = 3
        cls[(st[lv] == rule.ST_MISSING) & (J[lv] == rule.J_CONFLICT)] = 4
        cls[(st[lv] == rule.ST_MISSING) & ((J[lv] == rule.J_MIXED) | (J[lv] == rule.J_INSUFF))] = 5
        cls[st[lv] == rule.ST_INVISIBLE] = 6
        stp[okl] = cls
        stp[hit & ~okl] = 7
        # crop window around the projected neighbourhood
        half = row.get("half_m", 15.0)
        box = np.array([[cx - half, cy - half, zc], [cx + half, cy - half, zc], [cx + half, cy + half, zc], [cx - half, cy + half, zc]])
        u, v, z = V.project(n, box)
        x0, x1 = int(max(0, np.nanmin(u) - 10)), int(min(GRID_W, np.nanmax(u) + 10))
        y0, y1 = int(max(0, np.nanmin(v) - 10)), int(min(GRID_H, np.nanmax(v) + 10))
        if x1 - x0 < 40 or y1 - y0 < 40:
            x0, x1, y0, y1 = 0, GRID_W, 0, GRID_H
        img = cv2.imread(str(DENSE / "images" / n))[:, :, ::-1]
        img = cv2.resize(img, (GRID_W, GRID_H), interpolation=cv2.INTER_AREA)
        fig = plt.figure(figsize=(19, 3.9))
        gs = fig.add_gridspec(1, 6, width_ratios=[1, 1, 1, 1, 0.08, 1.7], wspace=0.07)
        axs = [fig.add_subplot(gs[i]) for i in range(4)]; ax5 = fig.add_subplot(gs[5])
        axs[0].imshow(img[y0:y1, x0:x1]); axs[0].set_title(f"현재 영상 {n[-12:-4]} (경사 {V.tilt(n):.0f}°)", fontsize=9)
        axs[1].imshow(np.where(a1, 1, 0)[y0:y1, x0:x1], cmap=ListedColormap(["#3b3b3b", "#f2d16b"]), vmin=0, vmax=1, interpolation="nearest")
        axs[1].set_title("관측 신뢰도 (노랑 = 1)", fontsize=9)
        mk = np.where(mark < 0, 0, mark + 1)
        axs[2].imshow(mk[y0:y1, x0:x1], cmap=ListedColormap(["#d9d9d9", "#2a9d3a", "#d62728"]), vmin=0, vmax=2, interpolation="nearest")
        axs[2].set_title("표시 (초록 일치 · 빨강 충돌 · 회색 없음)", fontsize=9)
        cmap = ListedColormap(["#ffffff", "#9ad19a", "#e8837e", "#2a9d3a", "#c00000", "#f0b429", "#4a6fd1", "#bdbdbd"])
        axs[3].imshow(np.where(stp < 0, 0, stp)[y0:y1, x0:x1], cmap=cmap, vmin=0, vmax=7, interpolation="nearest")
        axs[3].set_title("패치: 지지 일치/충돌 · 결측 전파 일치/충돌/미판정 · 비가시", fontsize=8)
        for ax_ in axs:
            ax_.set_xticks([]); ax_.set_yticks([])
        # mark the centre
        uc, vc, _ = V.project(n, Xc)
        for ax_ in axs:
            ax_.plot(uc[0] - x0, vc[0] - y0, "+", color="#d000d0", ms=12, mew=2)
        # section
        (ax_, ay_), (bx_, by_) = row["line"]
        L = float(np.hypot(bx_ - ax_, by_ - ay_)); s = np.arange(0, L, 0.1)
        px = ax_ + (bx_ - ax_) * s / L; py = ay_ + (by_ - ay_) * s / L
        tt, _ = sc.cast_points(np.column_stack([px, py, np.full(len(s), 250.0)]), np.tile([0, 0, -1.0], (len(s), 1)))
        zp = 250.0 - tt
        E = px + 690953.0; N = py + 5336071.0
        ix = np.clip(((E - 690700.0) / 0.5).astype(int), 0, Sv["dtm"].shape[1] - 1); iy = np.clip(((N - 5335820.0) / 0.5).astype(int), 0, Sv["dtm"].shape[0] - 1)
        base = float(np.nanmedian(Sv["dtm"][iy, ix])) - 604.0
        # MVS points of this view (confidence 1; the photometric depth of confidence-0 pixels in pale green) within 0.3 m of A -> B
        dvec = np.array([bx_ - ax_, by_ - ay_]) / L
        for dep, col, lab_, ms_ in ((np.where(a1, dm, np.nan), "#2a9d3a", "MVS 2024 (신뢰도 1, 이 시점)", 1.6),):
            okp = np.isfinite(dep) & (dep > 0)
            Xm = C[None, None, :] + np.where(okp, dep, 0)[..., None] * Dr.astype(np.float64)
            rel = Xm[..., :2] - np.array([ax_, ay_]); al = rel @ dvec; ac = rel @ np.array([-dvec[1], dvec[0]])
            mm = okp & (np.abs(ac) <= 0.3) & (al >= 0) & (al <= L)
            ax5.plot(al[mm], Xm[..., 2][mm] - base, ".", color=col, ms=ms_, label=lab_)
        pp = c["mvs"] / "stereo/depth_maps" / f"{n}.photometric.bin"
        if pp.exists():
            dph = read_depth_bin(pp); okp = np.isfinite(dph) & (dph > 0) & ~a1
            Xm = C[None, None, :] + np.where(okp, dph, 0)[..., None] * Dr.astype(np.float64)
            rel = Xm[..., :2] - np.array([ax_, ay_]); al = rel @ dvec; ac = rel @ np.array([-dvec[1], dvec[0]])
            mm = okp & (np.abs(ac) <= 0.3) & (al >= 0) & (al <= L)
            ax5.plot(al[mm], Xm[..., 2][mm] - base, ".", color="#a6dba0", ms=1.2, label="MVS 광도 깊이 (신뢰도 0)")
        # prior: intersection of the registered prior mesh with the vertical plane through A -> B (roofs and walls alike)
        Vp = pr.V0 + pr.shift; Fp = pr.F
        nrm2 = np.array([-dvec[1], dvec[0]])
        dv = (Vp[:, :2] - np.array([ax_, ay_])) @ nrm2
        av = (Vp[:, :2] - np.array([ax_, ay_])) @ dvec
        dt = dv[Fp]; at = av[Fp]
        near = (dt.min(1) < 0) & (dt.max(1) > 0) & (at.max(1) > -1) & (at.min(1) < L + 1)
        segs = []
        for f_ in Fp[near]:
            pts = []
            for i_, j_ in ((0, 1), (1, 2), (2, 0)):
                di, dj = dv[f_[i_]], dv[f_[j_]]
                if di * dj < 0:
                    w_ = di / (di - dj); P_ = Vp[f_[i_]] + (Vp[f_[j_]] - Vp[f_[i_]]) * w_
                    pts.append(((P_[:2] - np.array([ax_, ay_])) @ dvec, P_[2] - base))
            if len(pts) == 2:
                segs.append(pts)
        from matplotlib.collections import LineCollection
        if segs:
            ax5.add_collection(LineCollection(segs, colors="#e07b00" if prior == "LoD2" else "#1f5fbf", linewidths=1.8, zorder=6,
                                              label=f"사전 정보 {prior} (정합 뒤, 단면)"))
        ax5.set_xlim(0, L)
        if c["gtp"] is not None:
            G = c["gtp"]
            dvec = np.array([bx_ - ax_, by_ - ay_]) / L
            rel = G[:, :2] - np.array([ax_, ay_])
            along = rel @ dvec; across = rel @ np.array([-dvec[1], dvec[0]])
            mm = (np.abs(across) <= 0.25) & (along >= 0) & (along <= L)
            ax5.plot(along[mm], G[mm, 2] - base, "k.", ms=1.0, alpha=0.45, zorder=3, label="참값 (±0.25 m 띠)")
            zs = list(G[mm, 2] - base) + [q[1] for sg in segs for q in sg]
            if len(zs) > 10:
                lo_, hi_ = np.percentile(zs, 1), np.percentile(zs, 99)
                ax5.set_ylim(lo_ - 3.0, hi_ + 3.0)    # photometric outliers far outside are clipped from view
        ax5.set_xlabel("A → B 거리 (m)", fontsize=8); ax5.set_ylabel("지면 기준 높이 (m)", fontsize=8); ax5.grid(alpha=0.3)
        ax5.legend(fontsize=7, loc="upper right"); ax5.tick_params(labelsize=7)
        fig.suptitle(row.get("title", row["tid"]), fontsize=10.5, x=0.01, ha="left", y=1.05, weight="bold")
        if row.get("note"):
            fig.text(0.01, -0.05, row["note"], fontsize=8.5, ha="left")
        fig.savefig(O / f"{row['tid']}.png", dpi=105, bbox_inches="tight")
        plt.close(fig)
        print("row", row["tid"], n, flush=True)


if __name__ == "__main__":
    main()
