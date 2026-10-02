"""PHD-MAIN-PREP-DISCARD-RULE-v1 5.4: figure rows of the representative sites, every rule side by side (jointbuildgs:dev, CPU).

  python site_rows.py [--rules-sub rules] [--out-sub figs/sites]

Sites = configs/phd/main_prep_discard_rule_v1/sites_v1.json (membership rule there). Per site and prior one figure:
  top row   photo crop of the site's view (roof sites: the nadir training view with the most pixels on the site; wall sites: the
            view with the most pixels), observation confidence (yellow = 1), section through the site (prior mesh, the view's
            confidence-1 MVS, GT +- 0.25 m) — the same panels for every rule
  per rule  agree / conflict marks at the rule's threshold (green / red) and the patch state and decision (support agree /
            conflict, missing agree / conflict / undetermined, invisible) of that rule
Also sites.json: per site, prior and rule the decisions on the site's patches (measured / unmeasured, against the true label).
scientific_verdict: null."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import LineCollection
from matplotlib.colors import ListedColormap
import numpy as np

from common import CFG, OUT, PREP, REPO, GRID_H, GRID_W, DENSE, Scene, Views, jdump, log, read_depth_bin
from src.phd.prior_propagation_v5 import conversion as conv
from src.phd.prior_propagation_v5 import locations as locs
from src.phd.prior_propagation_v5 import rule
from src.phd.prior_propagation_v5 import rules as R
import s03_stage1 as s3

for f in ("/fonts/NotoSansCJK-Regular.ttc", "/fonts/NotoSansCJK-Bold.ttc"):
    try:
        font_manager.fontManager.addfont(f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

RULE_KO = {"current": "지금 규칙", "margin_all_1.5": "여유(모두) 1.5", "margin_all_2": "여유(모두) 2", "margin_all_3": "여유(모두) 3",
           "margin_prop_1.5": "여유(전파만) 1.5", "margin_prop_2": "여유(전파만) 2", "margin_prop_3": "여유(전파만) 3",
           "asymmetric": "비대칭", "tau_0.5": "허용 오차 0.5배", "tau_2": "허용 오차 2배"}
CLS_COL = ["#ffffff", "#9ad19a", "#e8837e", "#2a9d3a", "#c00000", "#f0b429", "#4a6fd1", "#bdbdbd"]


def run_paths(site, prior, rs):
    kind, rid = site["run"].split(":")
    if kind == "range":
        return OUT / "s52/s03" / rid / prior, OUT / "s52/gt" / rid, rid, OUT / "s02" / rid
    box = {"B173nb": "B173nb_b10", "B0": "B0_b10"}[rid]
    return OUT / "s52/box" / box / prior, OUT / "s52/box_gt" / box, box, OUT / "s02_box" / box


def site_members(site, prior, run_dir, mesh_dir):
    U = locs.load_store(run_dir / "units.npz")
    tab = {r["gml"]: r["ext"] for r in json.loads((mesh_dir / "lod2_surfaces.json").read_text())["surfaces"]}
    UL = U if prior == "LoD2" else locs.load_store(run_dir.parent / "LoD2" / "units.npz")
    exts = [tab[g] for g in site["faces_gml"]]
    mL = np.isin(UL["surf_ext"][UL["loc_surface"]], exts)
    if prior == "LoD2":
        return U, mL
    from scipy.spatial import cKDTree
    t = cKDTree(UL["loc_center"][mL, :2])
    d, _ = t.query(U["loc_center"][:, :2], k=1, distance_upper_bound=0.5)
    return U, np.isfinite(d)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--rules-sub", default="rules"); ap.add_argument("--out-sub", default="figs/sites")
    a = ap.parse_args()
    O = OUT / a.out_sub; O.mkdir(parents=True, exist_ok=True)
    sites = json.loads((REPO / "configs/phd/main_prep_discard_rule_v1/sites_v1.json").read_text())["sites"]
    V = Views()
    summary = {}
    for site in sites:
        for prior, expected in site["expected"].items():
            run_dir, gt_dir, rid, mesh_dir = run_paths(site, prior, None)
            U, mem = site_members(site, prior, run_dir, mesh_dir)
            dec = np.load(OUT / a.rules_sub / "decisions" / f"{rid}_{prior}.npz")
            G = np.load(gt_dir / f"labels_{prior}.npz"); lab = G["label"]
            if rid.startswith("B0") and (gt_dir / f"labels_uls_{prior}.npz").exists():
                Gu = np.load(gt_dir / f"labels_uls_{prior}.npz"); lab = np.where((lab < 0) & (Gu["label"] >= 0), Gu["label"], lab)
            st = U["state"]
            rec = {}
            pairs = dict(np.load(run_dir / "unit_view_pairs.npz")); kn = np.load(run_dir / "knn.npz")
            jc = CFG["judgment"]
            RS = {n: R.apply(pairs, len(st), kn["mis"], kn["k_dist"], kn["k_id"], n, jc["majority"], int(jc["min_evidence"]), float(jc["max_distance_m"])) for n in R.RULES}
            for n in R.RULES:
                d = dec[n]
                rr = {}
                for mn, sv in (("measured", rule.ST_SUPPORT), ("unmeasured", rule.ST_MISSING)):
                    m = mem & (st == sv)
                    rr[mn] = dict(n=int(m.sum()), discard=int((m & d).sum()), keep=int((m & ~d).sum()),
                                  discard_true_conflict=int((m & d & (lab == 1)).sum()), discard_true_agree=int((m & d & (lab == 0)).sum()),
                                  keep_true_agree=int((m & ~d & (lab == 0)).sum()), keep_true_conflict=int((m & ~d & (lab == 1)).sum()))
                rr["invisible"] = int((mem & (st == rule.ST_INVISIBLE)).sum())
                rec[n] = rr
            summary[f"{site['id']}/{prior}"] = dict(expected=expected, run=site["run"], patches=int(mem.sum()), rules=rec)
            # ---------------- figure
            summ = json.loads((run_dir / "summary.json").read_text())
            pr = s3.Prior(mesh_dir, prior); pr.shift = np.asarray(summ["registration"]["shift_applied"], float)
            sc, _ = pr.scene()
            tau = {1: summ["tolerance"]["roof"]["tau"], 2: summ["tolerance"]["wall"]["tau"]}
            wall = np.mean(U["loc_kind"][mem] == 2) > 0.5
            views = [str(v) for v in pairs["views"]]
            mm = np.isin(pairs["loc"], np.nonzero(mem)[0])
            s_ = np.bincount(pairs["view"][mm], weights=pairs["npix"][mm], minlength=len(views))
            order = np.argsort(-s_)
            cand = [views[i] for i in order if s_[i] > 0]
            if not wall:
                nad = [v for v in cand if V.tilt(v) <= 20.0]
                cand = nad or cand
            n = cand[0]
            Dr = V.rays(n); C = V.C(n)
            tP, tri = sc.cast(C, Dr)
            dm = read_depth_bin(Path(summ["mvs"]) / "stereo/depth_maps" / f"{n}.geometric.bin")
            a1 = np.isfinite(dm) & (dm > 0)
            hit = tri >= 0
            nn = np.zeros((GRID_H, GRID_W, 3)); nn[hit] = pr.n_used[tri[hit]]
            fct = conv.factor(nn, Dr.astype(np.float64), has_surface=hit)
            kind = conv.surface_kind(nn[..., 2])
            bf = np.zeros_like(hit); bf[hit] = pr.bface_tri[tri[hit]]
            tp = np.where(bf, np.where(kind == 1, tau[1], tau[2]), tau[1])
            rres = np.abs((dm - tP) * fct)
            ci = np.full(tri.shape, -1, np.int64); ci[hit] = pr.ci_of_tri[tri[hit]]
            X = C[None, None, :] + tP[..., None] * Dr.astype(np.float64)
            loc = np.full(tri.shape, -1, np.int64); okl = ci >= 0
            loc[okl] = locs.locate(U, ci[okl], X[okl])
            site_px = np.zeros(tri.shape, bool); site_px[okl] = mem[loc[okl]]          # pixels on the site's patches (outlined in every panel)
            P3 = U["loc_center"][mem]; P2 = P3[:, :2]
            # section centre = the member patch farthest from every non-member patch (the site's interior; the members' mean can lie
            # off a multi-part site and the patch nearest the mean sits on its edge; fix 06:50/06:55, presentation only), direction
            # from the members within 15 m of it
            from scipy.spatial import cKDTree
            others = U["loc_center"][~mem & U["loc_in_range"], :2]
            wall = np.mean(U["loc_kind"][mem] == 2) > 0.5
            if wall:     # walls overlap other faces in plan: centre = the member nearest the coordinate-wise median (mid-wall, not a corner)
                i0 = int(np.argmin(np.linalg.norm(P3 - np.median(P3, axis=0), axis=1)))
            elif len(others):
                din, _ = cKDTree(others).query(P2, k=1)
                i0 = int(np.argmax(din))
            else:
                c2 = P2.mean(0); i0 = int(np.argmin(np.linalg.norm(P2 - c2, axis=1)))
            cx, cy = P2[i0]; cz = float(P3[i0, 2])
            near_c = np.linalg.norm(P2 - P2[i0], axis=1) <= 15.0
            # crop = the site's pixels in this view + a margin (fix 06:50: the projected square could leave the site at the image edge)
            ys_, xs_ = np.nonzero(site_px)
            if len(xs_) >= 20:
                bw, bh = xs_.max() - xs_.min() + 1, ys_.max() - ys_.min() + 1
                m_ = int(max(30, 0.25 * max(bw, bh)))
                x0, x1, y0, y1 = xs_.min() - m_, xs_.max() + 1 + m_, ys_.min() - m_, ys_.max() + 1 + m_
                for lo, hi, lim in ((0, 1, GRID_W), (2, 3, GRID_H)):
                    q = [x0, x1, y0, y1]
                    if q[hi] - q[lo] < 200:
                        g_ = (200 - (q[hi] - q[lo])) // 2; q[lo] -= g_; q[hi] += g_
                    x0, x1, y0, y1 = q
                x0, x1, y0, y1 = int(max(0, x0)), int(min(GRID_W, x1)), int(max(0, y0)), int(min(GRID_H, y1))
            else:
                half = float(np.clip(np.ptp(P2, axis=0).max() / 2 + 5, 10, 35))
                box = np.array([[cx - half, cy - half, cz], [cx + half, cy - half, cz], [cx + half, cy + half, cz], [cx - half, cy + half, cz]])
                u_, v_, _ = V.project(n, box)
                x0, x1, y0, y1 = int(max(0, np.nanmin(u_) - 10)), int(min(GRID_W, np.nanmax(u_) + 10)), int(max(0, np.nanmin(v_) - 10)), int(min(GRID_H, np.nanmax(v_) + 10))
                if x1 - x0 < 40 or y1 - y0 < 40:
                    x0, x1, y0, y1 = 0, GRID_W, 0, GRID_H
            img = __import__("cv2").imread(str(DENSE / "images" / n))[:, :, ::-1]
            img = __import__("cv2").resize(img, (GRID_W, GRID_H), interpolation=__import__("cv2").INTER_AREA)
            names = list(R.RULES)
            fig = plt.figure(figsize=(2.3 * len(names), 9.0))
            gs = fig.add_gridspec(3, len(names), height_ratios=[1.25, 1, 1], hspace=0.28, wspace=0.05)
            ax0 = fig.add_subplot(gs[0, 0:2]); ax1 = fig.add_subplot(gs[0, 2:4]); axs = fig.add_subplot(gs[0, 5:])
            ax0.imshow(img[y0:y1, x0:x1]); ax0.set_title(f"사진 {n[-12:-4]} (경사 {V.tilt(n):.0f}°)", fontsize=9)
            ax1.imshow(np.where(a1, 1, 0)[y0:y1, x0:x1], cmap=ListedColormap(["#3b3b3b", "#f2d16b"]), vmin=0, vmax=1, interpolation="nearest")
            ax1.set_title("관측 신뢰도 (노랑 = 1)", fontsize=9)
            import cv2 as _cv2
            site_cl = _cv2.morphologyEx(site_px.astype(np.uint8), _cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)).astype(bool)   # one outline around many small faces

            def outline(ax_):
                sp = site_cl[y0:y1, x0:x1].astype(float)
                if sp.any():
                    ax_.contour(sp, levels=[0.5], colors="#d000d0", linewidths=0.9)
            for ax_ in (ax0, ax1):
                ax_.set_xticks([]); ax_.set_yticks([]); outline(ax_)
            for j, rn in enumerate(names):
                t_ = R.RULES[rn]["t"]
                mk = np.zeros(tri.shape, np.int8); mk[hit & a1 & (rres <= t_ * tp)] = 1; mk[hit & a1 & ~(rres <= t_ * tp)] = 2
                axm = fig.add_subplot(gs[1, j]); axm.imshow(mk[y0:y1, x0:x1], cmap=ListedColormap(["#d9d9d9", "#2a9d3a", "#d62728"]), vmin=0, vmax=2, interpolation="nearest")
                axm.set_title(RULE_KO[rn], fontsize=8.5); axm.set_xticks([]); axm.set_yticks([]); outline(axm)
                st_r, vote_r, J_r, _ = RS[rn]
                lv = loc[okl]; cls = np.zeros(len(lv), np.int8)
                cls[(st_r[lv] == rule.ST_SUPPORT) & (vote_r[lv] == rule.V_AGREE)] = 1
                cls[(st_r[lv] == rule.ST_SUPPORT) & (vote_r[lv] == rule.V_CONFLICT)] = 2
                cls[(st_r[lv] == rule.ST_MISSING) & (J_r[lv] == rule.J_AGREE)] = 3
                cls[(st_r[lv] == rule.ST_MISSING) & (J_r[lv] == rule.J_CONFLICT)] = 4
                cls[(st_r[lv] == rule.ST_MISSING) & ((J_r[lv] == rule.J_MIXED) | (J_r[lv] == rule.J_INSUFF))] = 5
                cls[st_r[lv] == rule.ST_INVISIBLE] = 6
                stp = np.zeros(tri.shape, np.int8); stp[okl] = cls; stp[hit & ~okl] = 7
                axp = fig.add_subplot(gs[2, j]); axp.imshow(stp[y0:y1, x0:x1], cmap=ListedColormap(CLS_COL), vmin=0, vmax=7, interpolation="nearest")
                axp.set_xticks([]); axp.set_yticks([]); outline(axp)
                r_ = rec[rn]; tot = r_["measured"]["n"] + r_["unmeasured"]["n"]
                dsc = r_["measured"]["discard"] + r_["unmeasured"]["discard"]
                axp.set_xlabel(f"버림 {dsc}/{tot}", fontsize=8)
            # section along the site's main axis (walls: across)
            if wall:
                # across the wall: the plan direction of least spread of the members near the centre (fix 06:59: the mean of the patch
                # normals can cancel when their signs differ, which put the B0 facade section along the wall)
                Pn = P2[near_c]; Q = Pn - Pn.mean(0); w_, vv = np.linalg.eigh(Q.T @ Q); nh = vv[:, 0]
                A_, B_ = np.array([cx, cy]) - 8 * nh, np.array([cx, cy]) + 8 * nh
            else:
                # roofs: the direction through the centre patch along which the most member patches lie within 0.5 m of the line (20 m
                # each way), so the section stays on the site; half length = the members' reach on it + 2 m (6 to 20 m)
                rel = P2 - P2[i0]; best = (-1, None, None)
                for ang in np.deg2rad(np.arange(0.0, 180.0, 7.5)):
                    d_ = np.array([np.cos(ang), np.sin(ang)]); al_ = rel @ d_; ac_ = rel @ np.array([-d_[1], d_[0]])
                    on = (np.abs(ac_) <= 0.5) & (np.abs(al_) <= 20.0)
                    if on.sum() > best[0]:
                        best = (int(on.sum()), d_, al_[on])
                dd = best[1]
                Lh = float(np.clip(np.abs(best[2]).max() + 2.0, 6, 20)) if best[2] is not None and len(best[2]) else 10.0
                A_, B_ = np.array([cx, cy]) - Lh * dd, np.array([cx, cy]) + Lh * dd
            # the section line on the photo (A, B at the centre patch's height)
            uab, vab, _ = V.project(n, np.array([[A_[0], A_[1], cz], [B_[0], B_[1], cz]]))
            if np.all(np.isfinite(uab)) and np.all(np.isfinite(vab)):
                uab, vab = uab - 0.5, vab - 0.5          # pixel i centre = coordinate i + 0.5 in Views.project
                ax0.plot(uab - x0, vab - y0, "-", color="#00e5ff", lw=1.4)
                for t_, uu, vv_ in (("A", uab[0], vab[0]), ("B", uab[1], vab[1])):
                    ax0.text(uu - x0, vv_ - y0, t_, color="#00e5ff", fontsize=9, weight="bold", ha="center", va="center", clip_on=True)
                ax0.set_xlim(0, x1 - x0); ax0.set_ylim(y1 - y0, 0)
            L = float(np.linalg.norm(B_ - A_)); dvec = (B_ - A_) / L; nrm2 = np.array([-dvec[1], dvec[0]])
            Vp = pr.V0 + pr.shift; Fp = pr.F
            dv = (Vp[:, :2] - A_) @ nrm2; av = (Vp[:, :2] - A_) @ dvec
            dt = dv[Fp]; at = av[Fp]
            near = (dt.min(1) < 0) & (dt.max(1) > 0) & (at.max(1) > -1) & (at.min(1) < L + 1)
            segs = []
            for f_ in Fp[near]:
                pts = []
                for i_, j_ in ((0, 1), (1, 2), (2, 0)):
                    di, dj = dv[f_[i_]], dv[f_[j_]]
                    if di * dj < 0:
                        w2 = di / (di - dj); P_ = Vp[f_[i_]] + (Vp[f_[j_]] - Vp[f_[i_]]) * w2
                        pts.append(((P_[:2] - A_) @ dvec, P_[2]))
                if len(pts) == 2:
                    segs.append(pts)
            zs = []
            if segs:
                axs.add_collection(LineCollection(segs, colors="#e07b00" if prior == "LoD2" else "#1f5fbf", linewidths=1.8, zorder=6, label=f"사전 정보 {prior}"))
                zs += [q[1] for sg in segs for q in sg]
            okp = a1
            Xm = C[None, None, :] + np.where(okp, dm, 0)[..., None] * Dr.astype(np.float64)
            rel = Xm[..., :2] - A_; al = rel @ dvec; ac = rel @ nrm2
            mq = okp & (np.abs(ac) <= 0.3) & (al >= 0) & (al <= L)
            axs.plot(al[mq], Xm[..., 2][mq], ".", color="#2a9d3a", ms=1.6, label="MVS (신뢰도 1, 이 시점)")
            gp = np.load(gt_dir / "gt_primary.npz")["xyz"]
            relg = gp[:, :2] - A_; alg = relg @ dvec; acg = relg @ nrm2
            mg = (np.abs(acg) <= 0.25) & (alg >= 0) & (alg <= L)
            axs.plot(alg[mg], gp[mg, 2], "k.", ms=1.0, alpha=0.45, label="참값 (±0.25 m)")
            zs += list(gp[mg, 2])
            if len(zs) > 10:
                zp = [q[1] for sg in segs for q in sg]          # the prior segments always inside the plot (fix 06:55)
                lo_ = min(np.percentile(zs, 1), min(zp) if zp else np.inf); hi_ = max(np.percentile(zs, 99), max(zp) if zp else -np.inf)
                axs.set_ylim(lo_ - 2, hi_ + 2)
            axs.set_xlim(0, L); axs.set_xlabel("A → B (m)", fontsize=8); axs.set_ylabel("높이 (m, 지역 틀)", fontsize=8)
            axs.legend(fontsize=7, loc="upper right"); axs.grid(alpha=0.3); axs.tick_params(labelsize=7)
            fig.suptitle(f"{site['id']} · {prior} · {site['run']} — 기대: {expected} (패치 {int(mem.sum())}개; 자홍 선 = 이 자리, 하늘색 A–B = 단면)", fontsize=11, x=0.01, ha="left", weight="bold")
            fig.savefig(O / f"site_{site['id']}_{prior}.png", dpi=90, bbox_inches="tight")
            plt.close(fig)
            log("site", site["id"], prior, n, int(mem.sum()))
    jdump(OUT / a.rules_sub / "sites.json", dict(rule=__doc__.split("\n\n")[1], sites=summary, scientific_verdict=None))


if __name__ == "__main__":
    main()
