"""What the photo-vs-prior conflicts are physically, where each result surface went, and how far the photo surface itself
sits from the GT (jointbuildgs:dev, CPU). scientific_verdict: null.

  python conflict_anatomy.py
Mounts: /s2 (payload, rw for eval/ and dashboard/), /artifacts/JointBuildGS (ro), /fonts (Noto CJK, ro).

Pixels, classes and distances are those of the intent table (eval_intent.py / make_intent_viewer.py): target roof and wall
pixels of the 15 views at training resolution; distances vertical on roofs and along the face normal on walls; signed
values + = above (roof) / outside (wall). Priors: M = old LoD2; L = old ALS as a 2.5D TIN, which has no vertical walls
(steep bridging triangles between roof-edge and ground points stand in for them).

1. eval/anatomy_faces_30000.csv      per prior (normal scene) and target face: class shares, the face's share of the
   region's conflict pixels, tau, prior - photo (A=1 pixels, no GT needed), and prior / photo / P / P0 / I relative to GT.
2. eval/anatomy_breakdown_30000.csv  per setting (M_N, M_B, L_N, L_B), region and place (faces; main roof split at 9 m
   before the hip end): conflict pixels, their share of the region's conflict row, share in the 0.5 m face-edge band,
   prior - photo, |prior - GT|, |photo - GT|, and per condition the followed share and |D - GT| = what the conflict row
   of the intent table is made of.
3. eval/anatomy_photo_vs_gt_30000.csv + figures/anatomy_photo_vs_gt.png  photo (MVS, A=1) - GT on the target roof agree
   pixels (LoD2), open ground and the front wall: a constant offset between the two data frames plus per-pixel scatter.
4. eval/figures/anatomy_{M,L}_{A_facade,B_roof_end}.png  photo crop + class tint + vertical sections (GT, photo surface,
   prior, P, P0 and I result surfaces of that prior, normal scene); copies and dashboard/intent/anatomy.js for intent.html.
5. eval/figures/anatomy_M_C_raised_roof.png  the injected scene (LoD2 with the main roof 3396 raised by 1 m): a cut across
   the main roof with the same layers (prior = the raised LoD2; P, P0 of that scene; I has no prior). Face medians in the
   box come from eval/faces_<it>.csv (d = prior - render, e = photo - render, g = GT - render).
The GT cloud (evaluation reference) is used for evaluation only."""
import os
import csv
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import open3d as o3d  # noqa: E402
from matplotlib import font_manager  # noqa: E402
GT_SET = os.environ.get("JBGS_GT_SET", "gt_clean")   # evaluation GT maps: gt_clean (visibility + ground datum, make_gt_clean.py) or gt (raw)

S2 = Path("/s2"); MAPS = S2 / "inputs/maps"; FIG = S2 / "eval/figures"; DASH = S2 / "dashboard/intent"
GT_RECEIPT = json.loads((MAPS / GT_SET / "receipt.json").read_text()) if (MAPS / GT_SET / "receipt.json").exists() else None
ART = Path("/artifacts/JointBuildGS")
POLYS = ART / "phase-payloads/phd/stage1_conf_tol_conflict_v1/PHD-STAGE1-CONF-TOL-CONFLICT-v1/inputs/lod2_polygons.json"
COND = ART / "phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921/conditions"
SPARSE, GT = COND / "B+1.0/scene/sparse_txt", COND / "N/evaluation/gt_cropped.ply"
PHOTOS = ART / "phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images"
IT, TRAIN, HALF = 30000, (1600, 1157), 0.25
SETTINGS = {"M_N": ["P_M_N", "P0_M_N", "O_M_N", "I"], "M_B": ["P_M_B", "P0_M_B", "O_M_B", "I"],
            "L_N": ["P_L_N", "P0_L_N", "I"], "L_B": ["P_L_B", "P0_L_B", "I"]}
PRIOR = {"M": dict(label="prior LoD2", short="LoD2", color="#1f5fbf"), "L": dict(label="prior ALS (2.5D TIN)", short="ALS", color="#7a3db8")}
CLS_RGB = {1: (66, 133, 244), 2: (255, 152, 0), 3: (156, 39, 176)}       # agree, conflict, unobserved (as the viewers)
PLACES = {0: ("roof", "건물 끝 경사면 (3404)"), 1: ("roof", "본지붕 중 건물 끝 9 m (3396)"), 2: ("roof", "본지붕 나머지 (3396)"),
          3: ("roof", "뒤쪽 날개 지붕 (3387·3389)"), 4: ("roof", "날개 옆 작은 면 (3394)"), 5: ("roof", "기타 지붕"),
          10: ("wall", "정면 벽 (3403)"), 11: ("wall", "건물 끝 벽 (3391)"), 12: ("wall", "기타 벽")}
BAND_PX = 11      # face-edge band at training resolution: ~0.46 m at 44 m (stage 1 used 40 px at full resolution)
END_X = -9.0      # main-roof split: the last 9 m before the hip end along the long axis (section 2 frame of face 3404)
font_manager.fontManager.addfont("/fonts/NotoSansCJK-Medium.ttc")
plt.rcParams["font.family"] = font_manager.FontProperties(fname="/fonts/NotoSansCJK-Medium.ttc").get_name()
FIG.mkdir(parents=True, exist_ok=True); DASH.mkdir(parents=True, exist_ok=True)
faces = json.loads((MAPS / "faces.json").read_text())
ROOF, WALL = [int(f) for f in faces["roof"]], [int(f) for f in faces["wall"]]
TGT = ROOF + WALL
PJ = {p["poly_index"]: p for p in json.loads(POLYS.read_text())["polygons"]}


class Med:
    """Streaming distribution in 1 mm bins over [-lim, lim] (outside values go to the end bins): median, MAD, histogram."""
    def __init__(self, lim=10.0, step=0.001):
        self.lim, self.step = lim, step
        self.h = np.zeros(int(round(2 * lim / step)) + 1, np.int64)

    def add(self, x):
        x = np.asarray(x, np.float64); x = x[np.isfinite(x)]
        if x.size:
            i = np.clip(np.round((x + self.lim) / self.step).astype(np.int64), 0, self.h.size - 1)
            self.h += np.bincount(i, minlength=self.h.size)

    @property
    def n(self):
        return int(self.h.sum())

    def centres(self):
        return np.arange(self.h.size) * self.step - self.lim

    def quantile(self, q):
        if not self.n:
            return None
        return float(self.centres()[int(np.searchsorted(np.cumsum(self.h), q * self.n))])

    def median(self):
        return self.quantile(0.5)

    def upto(self, vmax):
        """The same distribution without the values above vmax."""
        out = Med(self.lim, self.step); out.h = np.where(self.centres() <= vmax, self.h, 0)
        return out

    def mad(self):
        m = self.median()
        if m is None:
            return None
        d = np.abs(self.centres() - m); o = np.argsort(d, kind="stable")
        return float(d[o][int(np.searchsorted(np.cumsum(self.h[o]), 0.5 * self.n))])


def cm(x):
    return None if x is None else round(x * 100, 1)


def q2R(q):
    w, x, y, z = q
    return np.array([[1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w], [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
                     [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]])


KFULL = {}
for line in (SPARSE / "cameras.txt").read_text().splitlines():
    t = line.split()
    if t and not line.startswith("#"):
        fx, fy, cx, cy = map(float, t[4:8]); KFULL[t[0]] = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
calib = json.loads((S2 / "runs/P_M_N/scene/jbgs_calibration.json").read_text())["images"]
CAMS = {}
for line in (SPARSE / "images.txt").read_text().splitlines():
    t = line.split()
    if len(t) >= 10 and not line.startswith("#") and t[9].lower().endswith(".jpg"):
        name = Path(t[9]).stem
        CAMS[name] = dict(R=q2R([float(v) for v in t[1:5]]), t=np.array([float(v) for v in t[5:8]]),
                          K=np.array(calib[name]["K"]), Kfull=KFULL[t[8]])
VIEWS = sorted(CAMS)


def load(setname, view, size=None, dtype=np.float32):
    p = MAPS / setname / "raw_depth" / f"{view}.npy"
    x = np.load(p if p.exists() else MAPS / setname / f"{view}.npy").astype(np.float32)
    return (x if size is None else cv2.resize(x, size, interpolation=cv2.INTER_NEAREST)).astype(dtype)


def classes(A, M, P, T, F, extra=True):
    base = np.isin(F, TGT) & np.isfinite(P) & (P > 0) & np.isfinite(T) & extra
    hasM = np.isfinite(M) & (M > 0)
    c = np.zeros(F.shape, np.int8)
    c[base & (A > 0) & hasM & (np.abs(M - P) <= T)] = 1
    c[base & (A > 0) & hasM & (np.abs(M - P) > T)] = 2
    c[base & (A <= 0)] = 3
    return c


def frame(face):
    """Face centre c (xy), outward horizontal normal nh, horizontal direction along the face, ring (xy)."""
    ring = np.array(PJ[face]["ring_local_xy"]); n = np.array(PJ[face]["normal"], float)
    nh = n[:2] / max(np.linalg.norm(n[:2]), 1e-9)
    return ring.mean(0), nh, np.array([-nh[1], nh[0]]), ring


def coords(P, face, z0=0.0):
    c, nh, along, _ = frame(face)
    rel = P[..., :2] - c
    return rel @ along, rel @ nh, P[..., 2] - z0          # along the face, outward normal distance, height


def pixel_xyz(depth, cam):
    H, W = depth.shape; ys, xs = np.mgrid[0:H, 0:W]; K = cam["K"]
    return (np.stack([(xs - K[0, 2]) / K[0, 0] * depth, (ys - K[1, 2]) / K[1, 1] * depth, depth], -1) - cam["t"]) @ cam["R"]


def place_map(F, X):
    xend = coords(X, 3404)[1]
    pl = np.full(F.shape, -1, np.int8)
    pl[np.isin(F, ROOF)] = 5; pl[F == 3394] = 4; pl[np.isin(F, [3387, 3389])] = 3
    pl[F == 3396] = 2; pl[(F == 3396) & (xend > END_X)] = 1; pl[F == 3404] = 0
    pl[np.isin(F, WALL)] = 12; pl[F == 3391] = 11; pl[F == 3403] = 10
    return pl


def edge_band(F):
    band = np.zeros(F.shape, bool); k = np.ones((2 * BAND_PX + 1,) * 2, np.uint8)
    for f in np.unique(F[np.isin(F, TGT)]):
        m = (F == f).astype(np.uint8)
        band |= (m > 0) & (cv2.erode(m, k, borderType=cv2.BORDER_CONSTANT, borderValue=0) == 0)
    return band


samples = np.load(S2 / "inputs/points/prior_M_N.npz")["xyz"].astype(np.float64)
a_, x_, z_ = coords(samples, 3403)
Z0 = float(z_[(np.abs(a_) < 20) & (np.abs(x_) < 0.3)].min())          # base of the front wall 3403 = height 0
print("height reference (base of wall 3403, scene z):", round(Z0, 2), flush=True)

# ---------------------------------------------------------------- 1-3. one pass over the pixels of the 15 views
BD = {}                                        # (setting, place) -> accumulators
FACE_ACC = {}                                  # (prior, face) -> accumulators, normal scene
OFF = {k: Med(lim=2.0) for k in ("roof_agree", "ground", "wall")}
for v in VIEWS:
    cam = CAMS[v]
    A, M, G, FV = (load(s, v, TRAIN) for s in ("conf", "mvs", GT_SET, "fvert"))
    F = load("faceid", v, TRAIN, np.int32)
    hasM, hasG = np.isfinite(M) & (M > 0), np.isfinite(G) & (G > 0)
    PMN = load("prior_M_N", v, TRAIN)
    X = np.where(hasM[..., None], pixel_xyz(np.where(hasM, M, 0), cam), pixel_xyz(np.nan_to_num(PMN), cam))
    pl, band = place_map(F, X), edge_band(F)
    # photo - GT (+ = photo above / outside), the "source error" of the photos split into offset and scatter
    cMN = classes(A, M, PMN, load("tau_M", v, TRAIN), F)
    OFF["roof_agree"].add(((G - M) * FV)[np.isin(F, ROOF) & (cMN == 1) & hasG])
    OFF["wall"].add(((G - M) * FV)[(F == 3403) & (A > 0) & hasM & hasG])
    rw_z = np.abs((np.stack(np.meshgrid((np.arange(M.shape[1]) - cam["K"][0, 2]) / cam["K"][0, 0],
                                        (np.arange(M.shape[0]) - cam["K"][1, 2]) / cam["K"][1, 1]), -1) @ cam["R"][:2, 2])
                  + cam["R"][2, 2])                                   # vertical displacement per unit camera depth
    zrel = X[..., 2] - Z0
    ground = (F < 0) & (A > 0) & hasM & hasG & (zrel > -1.5) & (zrel < 1.0)
    OFF["ground"].add(((G - M) * rw_z)[ground])

    for setting, conds in SETTINGS.items():
        pr, sc = setting.split("_")
        P, T = load(f"prior_{pr}_{sc}", v, TRAIN), load(f"tau_{pr}", v, TRAIN)
        Ds = {c: np.load(S2 / "eval" / c / f"render_{IT}" / f"{v}_depth.npy") for c in conds}
        cls = classes(A, M, P, T, F, Ds[conds[0]] > 0)
        spm = (M - P) * FV                                     # prior - photo, + = prior above / outside
        ep, em = np.abs(P - G) * FV, np.abs(M - G) * FV
        conf = cls == 2
        for pid in PLACES:
            here = pl == pid
            mc = here & conf
            r = BD.setdefault((setting, pid), dict(n=0, nc=0, ncb=0, spm=Med(), ep=Med(), em=Med(),
                                                   fol={c: 0 for c in conds}, ed={c: Med() for c in conds}))
            r["n"] += int((here & (cls > 0)).sum()); r["nc"] += int(mc.sum()); r["ncb"] += int((mc & band).sum())
            if not mc.any():
                continue
            r["spm"].add(spm[mc]); r["ep"].add(ep[mc & hasG]); r["em"].add(em[mc & hasG])
            for c in conds:
                r["fol"][c] += int((mc & (Ds[c] > 0) & (np.abs(Ds[c] - M) <= T)).sum())
                r["ed"][c].add((np.abs(Ds[c] - G) * FV)[mc & hasG])
        if sc != "N":
            continue
        runs = {"P": f"P_{pr}_N", "P0": f"P0_{pr}_N", "I": "I"}
        for f in TGT:
            m = (F == f) & (cls > 0)
            if not m.any():
                continue
            r = FACE_ACC.setdefault((pr, f), dict(n=0, c=[0, 0, 0, 0], tau=Med(), pm=Med(),
                                                  **{k: Med() for k in ("prior", "photo", "P", "P0", "I")},
                                                  **{"c_" + k: Med() for k in ("prior", "photo", "P", "P0", "I")}))
            r["n"] += int(m.sum())
            for k in (1, 2, 3):
                r["c"][k] += int((m & (cls == k)).sum())
            r["tau"].add((T * FV)[m]); r["pm"].add(spm[m & (A > 0) & hasM])
            g, gc = m & hasG, m & hasG & conf
            for key, Xd in (("prior", P), ("photo", M), *((k, Ds[c]) for k, c in runs.items())):
                ok = hasM if key == "photo" else True
                r[key].add(((G - Xd) * FV)[g & ok]); r["c_" + key].add(((G - Xd) * FV)[gc & ok])
    print("pixels", v, flush=True)

# per-face table
conf_tot = {}
for (pr, f), r in FACE_ACC.items():
    reg = "roof" if f in ROOF else "wall"
    conf_tot[(pr, reg)] = conf_tot.get((pr, reg), 0) + r["c"][2]
table = []
for (pr, f), r in sorted(FACE_ACC.items()):
    reg = "roof" if f in ROOF else "wall"; n = r["n"]
    row = dict(prior=pr, face=f, region=reg, n_px=n, share_agree=r["c"][1] / n, share_conflict=r["c"][2] / n,
               share_unobserved=r["c"][3] / n, conflict_share_of_region=r["c"][2] / max(conf_tot[(pr, reg)], 1),
               tau_cm=cm(r["tau"].median()), prior_vs_photo_cm=cm(r["pm"].median()))
    for key in ("prior", "photo", "P", "P0", "I"):
        row[f"{key}_vs_gt_cm"] = cm(r[key].median()); row[f"conflict_{key}_vs_gt_cm"] = cm(r["c_" + key].median())
    table.append(row)
with (S2 / "eval" / f"anatomy_faces_{IT}.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(table[0])); w.writeheader(); w.writerows(table)
FACE = {(r["prior"], r["face"]): r for r in table}

# breakdown of the conflict row by place
breakdown, bd_rows = {}, []
for setting, conds in SETTINGS.items():
    for region in ("roof", "wall"):
        pids = [p for p, (reg, _) in PLACES.items() if reg == region]
        tot = sum(BD[(setting, p)]["nc"] for p in pids)
        rows = []
        for p in pids:
            r = BD[(setting, p)]
            if r["nc"] == 0:
                continue
            row = dict(setting=setting, region=region, place=PLACES[p][1], n_px=r["n"], n_conflict=r["nc"],
                       conflict_rate_in_place=r["nc"] / max(r["n"], 1), share_of_region_conflicts=r["nc"] / max(tot, 1),
                       edge_band_share=r["ncb"] / r["nc"], prior_minus_photo_cm=cm(r["spm"].median()),
                       prior_minus_photo_p10_cm=cm(r["spm"].quantile(0.1)), prior_minus_photo_p90_cm=cm(r["spm"].quantile(0.9)),
                       err_prior_cm=cm(r["ep"].median()), err_photo_cm=cm(r["em"].median()))
            for c in conds:
                row[f"followed_{c}"] = r["fol"][c] / r["nc"]; row[f"err_{c}_cm"] = cm(r["ed"][c].median())
            rows.append(row)
        breakdown.setdefault(setting, {})[region] = rows
        bd_rows += rows
with (S2 / "eval" / f"anatomy_breakdown_{IT}.csv").open("w", newline="") as fh:
    keys = []
    for r in bd_rows:
        keys += [k for k in r if k not in keys]
    w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(bd_rows)
for setting in SETTINGS:
    for region in ("roof", "wall"):
        for r in breakdown[setting][region]:
            print(setting, region, r["place"], f"{r['share_of_region_conflicts']:.0%} of conflicts, rate {r['conflict_rate_in_place']:.0%},"
                  f" edge {r['edge_band_share']:.0%}, prior-photo {r['prior_minus_photo_cm']} (p10 {r['prior_minus_photo_p10_cm']}, "
                  f"p90 {r['prior_minus_photo_p90_cm']}), err prior/photo {r['err_prior_cm']}/{r['err_photo_cm']}", flush=True)

# photo vs GT. 'front' drops values > +0.3 m: a GT point more than 0.3 m behind the photo surface. On roofs and open ground
# these are points of hidden surfaces (courtyard, far walls) that the sparse point projection lets through; on walls they
# also include real window recesses, so the wall is read without the cut.
LABEL_OFF = {"roof_agree": "지붕 일치 칸 (LoD2 기준, 연직)", "ground": "지면 (연직)", "wall": "정면 벽 (수평, 법선 방향)"}
off_rows = []
for k, mm in OFF.items():
    fr = mm.upto(0.3)
    off_rows.append(dict(surface=k, label=LABEL_OFF[k], n=mm.n, median_cm=cm(mm.median()), mad_cm=cm(mm.mad()),
                         p10_cm=cm(mm.quantile(0.1)), p90_cm=cm(mm.quantile(0.9)),
                         share_gt_behind_30cm=1 - fr.n / max(mm.n, 1), median_front_cm=cm(fr.median()), mad_front_cm=cm(fr.mad())))
    print("photo - GT", k, off_rows[-1], flush=True)
with (S2 / "eval" / f"anatomy_photo_vs_gt_{IT}.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(off_rows[0])); w.writeheader(); w.writerows(off_rows)
fig, ax = plt.subplots(figsize=(10, 5.2))
for (k, mm), row, col in zip(OFF.items(), off_rows, ("#e07b00", "#2e7d32", "#555555")):
    c = mm.centres(); h = mm.h.astype(float)
    step = 5                                                                       # 5 mm bins for the plot
    hb = h[: h.size // step * step].reshape(-1, step).sum(1); cb = c[: c.size // step * step].reshape(-1, step).mean(1)
    sel = (cb > -0.40) & (cb < 0.30)
    if k == "wall":
        med, mad, note = row["median_cm"], row["mad_cm"], "창 등 깊은 자리 포함"
    else:
        med, mad, note = row["median_front_cm"], row["mad_front_cm"], f"가려진 면의 참값 {row['share_gt_behind_30cm']:.0%} 제외"
    ax.plot(cb[sel] * 100, hb[sel] / hb.sum() / (step * 0.1), color=col, lw=2,
            label=f"{LABEL_OFF[k]}: 가운데 {med:+.1f} cm, 흩어짐 {mad:.1f} cm ({note})")
    ax.axvline(med, color=col, ls=":", lw=1.5)
ax.axvline(0, color="black", lw=1)
ax.set_xlabel("영상 표면 − 참값(LiDAR) 거리 (cm, + = 영상이 위 / 바깥)", fontsize=11)
ax.set_ylabel("분포 (정규화)", fontsize=11); ax.grid(alpha=0.3); ax.legend(fontsize=9, loc="upper right")
ax.set_title(("정리한 참값" if GT_RECEIPT else "원래 참값") + " 기준 — 같은 자리의 영상 표면과 참값의 차이: 가운데가 0에 가까울수록 두 자료의 기준면이 맞는다", fontsize=11.5)
fig.tight_layout(); fig.savefig(FIG / "anatomy_photo_vs_gt.png", dpi=110); plt.close(fig)
(DASH / "anatomy_photo_vs_gt.png").write_bytes((FIG / "anatomy_photo_vs_gt.png").read_bytes())


# ---------------------------------------------------------------- 4. sections with photo context (normal scene)
def lift(depth_of, mask_of):
    out = []
    for v in VIEWS:
        Dm = depth_of(v); H, W = Dm.shape
        ys, xs = np.nonzero(mask_of(v, (W, H)) & np.isfinite(Dm) & (Dm > 0))
        d = Dm[ys, xs]; cam = CAMS[v]; K = cam["K"]
        Xc = np.stack([(xs - K[0, 2]) / K[0, 0] * d, (ys - K[1, 2]) / K[1, 1] * d, d], 1)
        out.append((Xc - cam["t"]) @ cam["R"])
    return np.concatenate(out)


tgt_mask = lambda v, s: np.isin(load("faceid", v, s, np.int32), TGT)  # noqa: E731
GTN, PHOTO = "GT (평가용 참값 점군)", "영상 표면 (MVS, 잰 곳)"
GT_CLOUD = np.asarray(o3d.io.read_point_cloud(str(GT)).points).copy()
if GT_RECEIPT:
    GT_CLOUD[:, 2] += GT_RECEIPT["datum_shift_z_m"]                   # the cleaned GT: same datum as its depth maps
LAYERS = {GTN: GT_CLOUD,
          PHOTO: lift(lambda v: load("mvs", v, TRAIN), lambda v, s: tgt_mask(v, s) & (load("conf", v, s) > 0))}
I_LAYER = lift(lambda v: np.load(S2 / "eval" / "I" / f"render_{IT}" / f"{v}_depth.npy"), tgt_mask)   # no prior: one for all
for pr in PRIOR:
    LAYERS[("prior", pr)] = lift(lambda v, pr=pr: load(f"prior_{pr}_N", v, TRAIN), tgt_mask)
    for k in ("P", "P0"):
        LAYERS[(k, pr)] = lift(lambda v, k=k, pr=pr: np.load(S2 / "eval" / f"{k}_{pr}_N" / f"render_{IT}" / f"{v}_depth.npy"), tgt_mask)
    LAYERS[("I", pr)] = I_LAYER
LAYERS[("prior", "M_B")] = lift(lambda v: load("prior_M_B", v, TRAIN), tgt_mask)             # the injected scene (section 5)
for k in ("P", "P0"):
    LAYERS[(k, "M_B")] = lift(lambda v, k=k: np.load(S2 / "eval" / f"{k}_M_B" / f"render_{IT}" / f"{v}_depth.npy"), tgt_mask)
LAYERS[("I", "M_B")] = I_LAYER
print("layers lifted", flush=True)


def layer_style(key, pr):
    """pr = M or L (normal scene) or M_B (LoD2 with the main roof raised by 1 m)."""
    if key == GTN:
        return GTN, "#111111", 0.40, "-"
    if key == PHOTO:
        return PHOTO, "#ff9800", 0.30, "-"
    kind = key[0]
    if kind == "prior":
        return PRIOR[pr[0]]["label"] + (" (본지붕 1 m 올림)" if pr.endswith("_B") else ""), PRIOR[pr[0]]["color"], 0.5, "--"
    return ({"P": "P 판정 GS 결과", "P0": "P0 prior 강제 GS 결과", "I": "I 영상 GS 결과"}[kind],
            {"P": "#2ea043", "P0": "#dc2626", "I": "#8c8c8c"}[kind], 0.30, "-." if kind == "I" else "-")


def layer_keys(pr):
    return [GTN, PHOTO, ("P", pr), ("P0", pr), ("I", pr), ("prior", pr)]


def face_pixels(face):
    """(along, height, class) of the face's table pixels (LoD2 classes), placed where they look on the LoD2 face."""
    out = []
    for v in VIEWS:
        F, P = load("faceid", v, TRAIN, np.int32), load("prior_M_N", v, TRAIN)
        cls = classes(*(load(k, v, TRAIN) for k in ("conf", "mvs", "prior_M_N", "tau_M")), F)
        ys, xs = np.nonzero((F == face) & (cls > 0)); d = P[ys, xs]; cam = CAMS[v]; K = cam["K"]
        Xp = (np.stack([(xs - K[0, 2]) / K[0, 0] * d, (ys - K[1, 2]) / K[1, 1] * d, d], 1) - cam["t"]) @ cam["R"]
        a, _, z = coords(Xp, face, Z0)
        out.append(np.stack([a, z, cls[ys, xs]], 1))
    return np.concatenate(out)


def pier_offset(face, span=15.0):
    """Cut position along the facade (m from its centre): GT mostly on the flat wall (-0.32..-0.10 m from the LoD2 plane)
    and pixels mostly in the LoD2 conflict class (photos measured there). Score = flat-wall share x conflict share."""
    a, x, z = coords(LAYERS[GTN], face, Z0)
    pa, pz, pc = face_pixels(face).T
    best = (0.0, -1.0, 0.0, 0.0)
    for s in np.arange(-span, span + 1e-9, 0.1):
        m = (np.abs(a - s) < HALF) & (z > 1) & (z < 18) & (x > -1) & (x < 0.5)
        q = (np.abs(pa - s) < HALF) & (pz > 1) & (pz < 18)
        if m.sum() >= 400 and q.sum() >= 2000:
            flat, conf = float(((x[m] > -0.32) & (x[m] < -0.10)).mean()), float((pc[q] == 2).mean())
            if flat * conf > best[1]:
                best = (float(s), flat * conf, flat, conf)
    return best


def median_line(x, z, axis, step, lo, hi, min_n=8):
    key, val = (z, x) if axis == "z" else (x, z)
    edges = np.arange(lo, hi + step, step); cs, ms = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (key >= a) & (key < b)
        if m.sum() >= min_n:
            cs.append((a + b) / 2); ms.append(np.median(val[m]))
    return (np.array(ms), np.array(cs)) if axis == "z" else (np.array(cs), np.array(ms))


def section_panel(ax, pr, face, win, axis, stretch, offset=0.0, title="", box="", xlabel=""):
    cut = {}
    for key in layer_keys(pr):
        name, col, al, ls = layer_style(key, pr)
        a, x, z = coords(LAYERS[key], face, Z0)
        m = (np.abs(a - offset) < HALF) & (x > win[0]) & (x < win[1]) & (z > win[2]) & (z < win[3])
        ax.scatter(x[m], z[m], s=1.5, c=col, alpha=al, rasterized=True, linewidths=0, zorder=2)
        lo, hi = (win[2], win[3]) if axis == "z" else (win[0], win[1])
        lx, lz = median_line(x[m], z[m], axis, 0.25 if axis == "z" else 0.2, lo, hi)
        ax.plot(lx, lz, color=col, lw=2.6 if ls == "--" else 2.0, ls=ls, zorder=5 if ls == "--" else 3, label=name)
        cut[key] = LAYERS[key][m]
    ax.set_xlim(win[0], win[1]); ax.set_ylim(win[2], win[3])
    if not stretch:
        ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(xlabel, fontsize=11); ax.set_ylabel("높이 (m, 정면 벽 밑변 = 0)", fontsize=11); ax.grid(alpha=0.3)
    ax.set_title(title, fontsize=11.5)
    ax.legend(loc="lower left", fontsize=9, framealpha=0.92)
    if box:
        ax.text(0.99, 0.99, box, transform=ax.transAxes, fontsize=9.5, ha="right", va="top",
                bbox=dict(boxstyle="round", fc="white", ec="#bbbbbb", alpha=0.95), zorder=6)
    return cut


def facade_hist(ax, pr, face):
    c, nh, along, ring = frame(face)
    s = (ring - c) @ along; lo, hi = s.min() + 0.5, s.max() - 0.5
    bins = np.arange(-1.0, 0.5001, 0.01); ctr = (bins[:-1] + bins[1:]) / 2
    peaks = {}
    for key in layer_keys(pr):
        name, col, _, ls = layer_style(key, pr)
        a, x, z = coords(LAYERS[key], face, Z0)
        m = (a > lo) & (a < hi) & (x > -1.0) & (x < 0.5) & (z > 0.5) & (z < 18.5)
        h, _ = np.histogram(x[m], bins=bins, density=True)
        if pr == "M" and key == ("prior", pr):
            ax.axvline(0, color=col, ls="--", lw=2.6, label=f"{name} 벽면 (0)")
            continue
        peaks[key] = ctr[np.argmax(h)]
        ax.plot(ctr, h, color=col, lw=2.4 if ls == "--" else 2, ls=ls,
                label=f"{name} — 가장 많은 자리 {peaks[key] * 100:+.0f} cm, 10~90 % {np.percentile(x[m], 10) * 100:+.0f}~{np.percentile(x[m], 90) * 100:+.0f} cm")
    if pr != "M":
        ax.axvline(0, color="#1f5fbf", ls=":", lw=1.4, label="LoD2 벽면 (위치 기준선)")
    ax.set_xlim(-1.0, 0.5); ax.set_xlabel("LoD2 벽면에서의 거리 (m, − = 건물 안쪽)", fontsize=11)
    ax.set_ylabel("분포 (정규화)", fontsize=11); ax.grid(alpha=0.3); ax.legend(loc="upper left", fontsize=8.8, framealpha=0.92)
    ax.set_title(f"정면 벽 전체: 각 표면이 어디쯤 있나 ({PRIOR[pr]['short']} 조건)", fontsize=11.5)


def project_full(X, view):
    cam = CAMS[view]; Xc = X @ cam["R"].T + cam["t"]; K = cam["Kfull"]
    Xc = Xc[Xc[:, 2] > 0]
    return np.stack([K[0, 0] * Xc[:, 0] / Xc[:, 2] + K[0, 2], K[1, 1] * Xc[:, 1] / Xc[:, 2] + K[1, 2]], 1)


def photo_crop(pr, view, crop_faces, pad=0.08, width=1400, scene="N"):
    im = cv2.cvtColor(cv2.imread(str(PHOTOS / f"{view}.JPG")), cv2.COLOR_BGR2RGB)
    F = load("faceid", view, None, np.int32)
    cls = classes(*(load(k, view) for k in ("conf", "mvs", f"prior_{pr}_{scene}", f"tau_{pr}")), F)
    ys, xs = np.nonzero(np.isin(F, crop_faces)); H, W = F.shape
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    ph, pw = int((y1 - y0) * pad), int((x1 - x0) * pad)
    y0, y1, x0, x1 = max(0, y0 - ph), min(H, y1 + ph), max(0, x0 - pw), min(W, x1 + pw)
    tint = im.astype(np.float32)
    for k, col in CLS_RGB.items():
        tint[cls == k] = 0.45 * tint[cls == k] + 0.55 * np.array(col, np.float32)
    raw, tint = im.copy(), tint.astype(np.uint8)
    th = max(3, int((x1 - x0) / width * 2.0))
    for img in (raw, tint):
        for f in TGT:
            cs, _ = cv2.findContours((F == f).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(img, cs, -1, (255, 255, 255), th)
    s = width / (x1 - x0)
    return [cv2.resize(x[y0:y1, x0:x1], None, fx=s, fy=s, interpolation=cv2.INTER_AREA) for x in (raw, tint)], (x0, y0, s)


def photo_column(fig, spec, pr, view, crop_faces, cuts, scene="N"):
    (raw, tint), (x0, y0, s) = photo_crop(pr, view, crop_faces, scene=scene)
    sub = spec.subgridspec(2, 1, hspace=0.10)
    lab = PRIOR[pr]["short"] + (" · 본지붕 +1 m" if scene == "B" else "")
    for i, (img, cap) in enumerate(((raw, "영상 (흰 선 = LoD2 면 경계, 색 점선 = 단면 위치)"),
                                    (tint, f"판정 ({lab}): 파랑 일치 · 주황 충돌 · 보라 미측정"))):
        ax = fig.add_subplot(sub[i]); ax.imshow(img); ax.set_axis_off(); ax.set_title(cap, fontsize=11)
        for xyz, label, col in cuts:
            uv = (project_full(xyz, view) - [x0, y0]) * s
            uv = uv[(uv[:, 0] > 0) & (uv[:, 0] < img.shape[1]) & (uv[:, 1] > 0) & (uv[:, 1] < img.shape[0])]
            if len(uv):
                ax.scatter(uv[:, 0], uv[:, 1], s=1.0, c=col, alpha=0.9, linewidths=0)
                j = np.argmin(uv[:, 1])
                ax.annotate(label, uv[j], xytext=(0, 10), textcoords="offset points", ha="center", fontsize=14,
                            color=col, fontweight="bold", bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=col, alpha=0.9))


def fn(pr, f):
    r = FACE[(pr, f)]
    return (f"{PRIOR[pr]['short']} {r['prior_vs_gt_cm']:+.0f} · 영상 {r['photo_vs_gt_cm']:+.0f} · "
            f"P {r['P_vs_gt_cm']:+.0f} · P0 {r['P0_vs_gt_cm']:+.0f} · I {r['I_vs_gt_cm']:+.0f}")


def save(fig, key):
    fig.savefig(FIG / f"anatomy_{key}.png", dpi=110, bbox_inches="tight"); plt.close(fig)
    (DASH / f"anatomy_{key}.png").write_bytes((FIG / f"anatomy_{key}.png").read_bytes())
    print("wrote", key, flush=True)


def bd(setting, region, place_prefix):
    return next(r for r in breakdown[setting][region] if r["place"].startswith(place_prefix))


off, _, flat, conf = pier_offset(3403)
print(f"facade cut at {off:+.1f} m from the face centre ({flat:.0%} of GT on the flat wall band, {conf:.0%} LoD2 conflict pixels)")
facts = {}
for pr in PRIOR:
    lab = PRIOR[pr]["short"]
    # ① front wall 3403: a cut through a flat wall pier + the distribution over the whole facade
    fig = plt.figure(figsize=(23, 8.8))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.3, 0.75, 1.0], wspace=0.22)
    cut = section_panel(fig.add_subplot(gs[0, 1]), pr, 3403, (-0.9, 0.5, -0.5, 19.5), "z", True, off,
                        title="벽 기둥을 지나는 수직 단면 (가로 확대)",
                        box=f"면 3403 전체 픽셀 중앙값\nGT 기준 cm (바깥 +)\n{fn(pr, 3403)}",
                        xlabel="LoD2 벽면에서의 거리 (m, − = 건물 안쪽)")
    axh = fig.add_subplot(gs[0, 2]); facade_hist(axh, pr, 3403)
    if pr == "M":
        axh.annotate("P의 작은 봉우리: 미측정 자리(무늬 없는 벽면, 보라)에서\n규칙대로 prior를 유지한 픽셀", xy=(-0.04, 3.2), xytext=(-0.95, 12),
                     fontsize=9.5, color="#2ea043", arrowprops=dict(arrowstyle="->", color="#2ea043"))
    photo_column(fig, gs[0, 0], pr, "DJI_20241217101313_0009_D", [3403, 3396], [(cut[("prior", pr)], "①", "#e6003c")])
    w = bd(f"{pr}_N", "wall", "정면 벽")
    if pr == "M":
        title = f"① 정면 벽 (벽 충돌 픽셀의 {w['share_of_region_conflicts']:.0%}가 이 면) — LoD2 벽면이 실제 평벽보다 약 20 cm 바깥에 놓여 있다"
    else:
        title = (f"① 정면 벽 (벽 충돌 픽셀의 {w['share_of_region_conflicts']:.0%}) — ALS 2.5D TIN에는 수직 벽이 없다: 벽 자리는 처마 끝 점과 땅 점을 "
                 f"잇는 가파른 삼각형이라 실제 평벽보다 대개 {w['prior_minus_photo_cm']:.0f} cm쯤 바깥이고, 들쭉날쭉하다 "
                 f"(10~90 %: {w['prior_minus_photo_p10_cm']:+.0f}~{w['prior_minus_photo_p90_cm']:+.0f} cm)")
    fig.suptitle(title, fontsize=15, x=0.01, ha="left")
    save(fig, f"{pr}_A_facade")

    # ②③ end of the building: the hip 3404 (+ the end of the main roof 3396) and the rear wing 3387/3389
    fig = plt.figure(figsize=(23, 8.8))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.1, 1.3, 0.8], wspace=0.2)
    cut2 = section_panel(fig.add_subplot(gs[0, 1]), pr, 3404, (-11.5, 2.8, 17.0, 23.7), "x", False,
                         title="② 끝 경사면 3404를 지나는 긴 축 방향 단면",
                         box=f"면 3404 전체 픽셀 중앙값, GT 기준 cm (위 +)\n{fn(pr, 3404)}",
                         xlabel="건물 긴 축 방향 위치 (m)")
    cut3 = section_panel(fig.add_subplot(gs[0, 2]), pr, 3387, (-11.0, 4.5, 17.5, 22.2), "x", True,
                         title="③ 날개 지붕 3387·3389를 가로지르는 단면 (세로 확대)",
                         box=f"GT 기준 중앙값 cm (위 +)\n3387: {fn(pr, 3387)}\n3389: {fn(pr, 3389)}",
                         xlabel="날개 지붕을 가로지르는 위치 (m)")
    photo_column(fig, gs[0, 0], pr, "DJI_20241217101333_0019_D", [3404, 3387, 3389],
                 [(cut2[("prior", pr)], "②", "#e6003c"), (cut3[("prior", pr)], "③", "#b000d0")])
    gx, gz = median_line(coords(cut2[GTN], 3404, Z0)[1], cut2[GTN][:, 2] - Z0, "x", 0.2, -11.5, 1.0)
    lx, lz = median_line(coords(cut2[("prior", pr)], 3404, Z0)[1], cut2[("prior", pr)][:, 2] - Z0, "x", 0.2, -11.5, 1.0)
    common = np.intersect1d(np.round(gx, 2), np.round(lx, 2))
    excess = np.array([lz[np.isclose(lx, c)][0] - gz[np.isclose(gx, c)][0] for c in common])
    facts[pr] = dict(hip_max_excess_m=float(excess.max()), hip_max_excess_at_m=float(common[int(np.argmax(excess))]),
                     hip_median_excess_m=float(np.median(excess)))
    print(pr, "section 2 prior - GT:", {k: round(v, 2) for k, v in facts[pr].items()}, flush=True)
    rows = breakdown[f"{pr}_N"]["roof"]; tot_c = sum(r["n_conflict"] for r in rows)
    edge = sum(r["edge_band_share"] * r["n_conflict"] for r in rows) / max(tot_c, 1)
    facts[pr]["roof_conflict_edge_band_share"] = edge
    if pr == "M":
        title = (f"②③ 건물 끝 지붕 — ② LoD2의 끝 경사면이 짧고 가팔라 실제보다 최대 약 {facts[pr]['hip_max_excess_m']:.1f} m 높다 · "
                 f"③ 날개 지붕은 LoD2가 실제보다 낮다")
    else:
        title = (f"②③ 건물 끝 지붕 — ALS는 끝 경사면·날개 지붕의 모양을 따라간다; ALS 지붕 충돌 픽셀의 {edge:.0%}는 "
                 f"면 가장자리 0.5 m 띠(처마·용마루·면 경계)에 있다")
    fig.suptitle(title, fontsize=15, x=0.01, ha="left")
    save(fig, f"{pr}_B_roof_end")

# ④ the injected scene (LoD2, main roof 3396 raised by 1 m): a cut across the main roof where the photos measure most
FB = {r["condition"]: r for r in csv.DictReader((S2 / "eval" / f"faces_{IT}.csv").open()) if r["face"] == "3396"}
fb = lambda c, k: float(FB[c][k]) * 100  # noqa: E731
c3, nh3, al3, ring3 = frame(3396)
xr, ar = (ring3 - c3) @ nh3, (ring3 - c3) @ al3
zroof = float(PJ[3396]["z_local_mean"]) - Z0
pa, px, pz = coords(LAYERS[PHOTO], 3396, Z0)
near = (px > xr.min()) & (px < xr.max()) & (np.abs(pz - zroof) < 4)
cut_at = float(max(np.arange(ar.min() + 2, ar.max() - 2, 0.25), key=lambda s: int((near & (np.abs(pa - s) < HALF)).sum())))
ga, gx, gz = coords(LAYERS[GTN], 3396, Z0)
gm = (np.abs(ga - cut_at) < HALF) & (gx > xr.min()) & (gx < xr.max()) & (np.abs(gz - zroof) < 4)
ra, rx, rz = coords(LAYERS[("prior", "M_B")], 3396, Z0)
rm = (np.abs(ra - cut_at) < HALF) & (rx > xr.min()) & (rx < xr.max())
win = (float(xr.min()) - 1.0, float(xr.max()) + 1.0, float(gz[gm].min()) - 0.6, float(rz[rm].max()) + 0.6)
print(f"main roof cut at {cut_at:+.2f} m along the face, window {tuple(round(w, 2) for w in win)}", flush=True)
fig = plt.figure(figsize=(23, 8.8))
gs = fig.add_gridspec(1, 2, width_ratios=[1.5, 1.2], wspace=0.12)
cut4 = section_panel(fig.add_subplot(gs[0, 1]), "M_B", 3396, win, "x", False, cut_at,
                     title="④ 본지붕 3396을 가로지르는 단면 (용마루 ↔ 처마)",
                     box=(f"면 3396 전체 픽셀 중앙값, GT 기준 cm (위 +)\nLoD2(+1 m) {fb('P_M_B', 'd') - fb('P_M_B', 'g'):+.0f} · "
                          f"영상 {fb('P_M_B', 'e') - fb('P_M_B', 'g'):+.0f} · P {-fb('P_M_B', 'g'):+.0f} · P0 {-fb('P0_M_B', 'g'):+.0f} · "
                          f"I {-fb('I', 'g'):+.0f}"),
                     xlabel="본지붕 경사 방향 위치 (m, + = 처마 쪽)")
photo_column(fig, gs[0, 0], "M", "DJI_20241217101313_0009_D", [3396], [(cut4[("prior", "M_B")], "④", "#e6003c")], scene="B")
fig.suptitle("④ 1 m 올린 본지붕 (LoD2 · 본지붕 +1 m 주입) — 틀린 prior를 영상이 잰 자리", fontsize=15, x=0.01, ha="left")
save(fig, "M_C_raised_roof")

(DASH / "anatomy.js").write_text("window.ANATOMY = " + json.dumps(dict(
    priors={pr: dict(faces=[r for r in table if r["prior"] == pr and r["n_px"] >= 10000],
                     figures=[f"anatomy_{pr}_A_facade.png", f"anatomy_{pr}_B_roof_end.png"], facts=facts[pr]) for pr in PRIOR},
    breakdown=breakdown, photo_vs_gt=dict(rows=off_rows, figure="anatomy_photo_vs_gt.png"), gt_set=GT_SET,
    gt_clean=({k: GT_RECEIPT[k] for k in ("datum_shift_z_m", "k_px", "behind_m", "photo_minus_gt_m")} if GT_RECEIPT else None),
    facade_cut_offset_m=off, height_reference_scene_z=Z0, edge_band_px=BAND_PX, main_roof_split_m=END_X),
    ensure_ascii=False) + ";\n")
print("done")
