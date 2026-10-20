"""PHD-MAIN-FIXTEST-v1 order 11.2: the place, view and panels of figures 0-5, fixed BEFORE any training of this task, from the region
files and the ground truth only (jointbuildgs:dev, CPU; no training, no GPU, no render; no value of any training result is used).

  CPUS=8 MEM=24 bash run_cpu_ft.sh figpos figpos_ft.py

Inputs (read only): S1 region files (regions_v3), S1 defs (rows_<prior>.npz, gt_classes.npz, prior_<prior>.npz), stage-0 units / store,
the fill task's obs_masked and undecidable masks (SL/work), the fill task's undecidable definitions and figure place (SL/prep), the
stage-2 measure files of figure 1 (only their row-index array 'gentle_row', and the 'new' reading of the two pre-training prior meshes
surface_ALS / samepath_ALS for the anchor of the vertical lines), this task's pre-training dry judgment of r16B (R1 LoD2;
own_depth_changed). Rules:
  fig 1  the 32,932 rows of the stage-2 decision-6 figure (figs_s2.band_B173): measure_s2.py:93 gentle rows (code 2, roof-like, outside
         band v2, slope <= 17 deg, thinned) with surf_ext == 1 (figs_s2.face_rows); the reading 'new' checked on the prior surface.
  fig 2  '영상이 틀린 곳' = dist71 dm_common.Unit.img (checked by importing it); patches joined at centre distance <= 0.36 m (3-D, as
         figdefs_s2.components); clusters of area >= 1 m^2 whose patches carry no gt_suspect (the multi-layer GT flag the fill task used);
         the one with the most GT points (region 'gt_points'); a 12 m x 0.5 m section through its mean patch centre along the principal
         axis of its patch centres in plan; z range from the GT, the prior and the MVS in the band (stage-2 section rule, inputs only).
  fig 3  R1 LoD2 missing patches (in_eval, code 4 / 13); extent = their centres' box + 3 m; the dots = own_depth_changed of the r16B dry
         judgment (patch order checked against the region file and the store).
  fig 4  B173 주변 ALS skylight case region + its 2 m band of the fill task (masks of SL/work/undecidable), the fill task's undecidable_aux
         extent; their missing patches (code 4 / 13).
  fig 0, fig 5  definitions only (no place).
Writes /out/prep/figpos.json, /out/prep/figpos_fig1_rows.npz, /out/prep/figpos_fig2_rows.npz. scientific_verdict: null."""
import datetime as dt
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

sys.path.insert(0, "/repo")
PH = Path("/ph")
S1 = Path("/s1")
S0 = Path("/s0")
OUT = Path("/out")
S2 = PH / "main_stage2_v1/PHD-MAIN-STAGE2-v1"
SL = PH / "main_fill_v1/PHD-MAIN-FILL-v1"
PREP = OUT / "prep"
KST = dt.timezone(dt.timedelta(hours=9))
OFFSET = (690953.0, 5336071.0)
T0 = time.time()
CHECKS = []


def now():
    return dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def log(*a):
    print(f"[{time.time() - T0:7.1f}s]", *a, flush=True)


def short(p):
    s = str(p)
    for k, v in ((str(S2) + "/", "S2/"), (str(SL) + "/", "SL/"), ("/s1/", "S1/"), ("/s0/", "S0/"), ("/out/", "FT/"), ("/repo/", "")):
        s = s.replace(k, v)
    return s


def sha(p, limit=300_000_000):
    p = Path(p)
    st = p.stat()
    out = dict(path=short(p), bytes=int(st.st_size), mtime=dt.datetime.fromtimestamp(st.st_mtime, KST).strftime("%Y-%m-%d %H:%M:%S KST"))
    if st.st_size <= limit:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 22), b""):
                h.update(b)
        out["sha256"] = h.hexdigest()
    return out


def check(name, ok, **detail):
    CHECKS.append(dict(check=name, ok=bool(ok), **detail))
    log("check", name, "OK" if ok else "FAILED", detail if not ok else "")
    return bool(ok)


def r3(x):
    return [round(float(v), 3) for v in np.asarray(x, np.float64).ravel()]


def counts(a):
    return {str(k): int(v) for k, v in sorted(Counter(np.asarray(a).tolist()).items())}


def region(site, prior):
    return np.load(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz")


def gt_xyz(site):
    """stage-1 GT points of the site (figs_s2.gt_points / measure_s2.rows_of): {src: xyz float64}."""
    G = np.load(S1 / "defs" / site / "gt_classes.npz")
    X = {0: G["xyz_gt_points"].astype(np.float64)}
    if "xyz_gt_primary" in G.files:
        X[1] = G["xyz_gt_primary"].astype(np.float64)
    return X


def rows_xyz(r, X):
    P = np.zeros((len(r["point"]), 3))
    src = r["src"]
    for s, A in X.items():
        m = src == s
        P[m] = A[r["point"][m]]
    return P


def corners_xy(U, idx):
    """plan corners of the patches (centre +- sp/2 t1 +- sp/2 t2; LoD2: unit face axes, ALS: the xy grid cell), 4 x 2 per patch."""
    h = 0.5 * float(U["sp"])
    c, t1, t2 = U["loc_center"][idx], U["loc_t1"][idx], U["loc_t2"][idx]
    out = np.stack([c - h * t1 - h * t2, c + h * t1 - h * t2, c + h * t1 + h * t2, c - h * t1 + h * t2], 1)[:, :, :2]
    return np.round(out, 3)


def components(C, radius):
    if len(C) == 0:
        return 0, np.zeros(0, int)
    pairs = cKDTree(C).query_pairs(radius, output_type="ndarray")
    A = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(C), len(C)))
    return connected_components(A, directed=False)


def plane_segments(V, F, c, t, L):
    """figs_s2.plane_segments: the triangles crossing the vertical plane through c along t, as (s, z) segments with |s| <= L."""
    npn = np.array([-t[1], t[0], 0.0])
    d = (V - c) @ npn
    dt_ = d[F]
    cross = (dt_.min(1) < 0) & (dt_.max(1) > 0)
    F_, d_ = F[cross], dt_[cross]
    ms, Xs = [], []
    for a, b_ in ((0, 1), (1, 2), (2, 0)):
        m = (d_[:, a] < 0) != (d_[:, b_] < 0)
        w = d_[:, a] / np.where(m, d_[:, a] - d_[:, b_], 1.0)
        ms.append(m)
        Xs.append(V[F_[:, a]] + w[:, None] * (V[F_[:, b_]] - V[F_[:, a]]))
    ms = np.stack(ms, 1)
    Xs = np.stack(Xs, 1)
    ok = ms.sum(1) == 2
    idx = np.argsort(~ms[ok], axis=1, kind="stable")[:, :2]
    X2 = np.take_along_axis(Xs[ok], idx[:, :, None].repeat(3, 2), 1)
    sv = (X2[..., :2] - c[:2]) @ t[:2]
    seg = np.stack([sv, X2[..., 2]], -1)
    return seg[np.abs(sv).min(1) <= L]


def crop_mesh(V, F, c, R):
    T = V[F][:, :, :2]
    lo, hi = T.min(1), T.max(1)
    keep = (lo[:, 0] <= c[0] + R) & (hi[:, 0] >= c[0] - R) & (lo[:, 1] <= c[1] + R) & (hi[:, 1] >= c[1] - R)
    return V, F[keep]


def hist_mode(v_cm):
    """the stage-2 histogram of figs_s2.band_B173: bins 0.5 cm on [-15, 20] cm, values clipped into the range; mode = fullest bin centre."""
    bins = np.arange(-15, 20.01, 0.5)
    v = v_cm[np.isfinite(v_cm)]
    h, _ = np.histogram(np.clip(v, bins[0], bins[-1]), bins)
    k = int(np.argmax(h))
    med = float(np.median(v))
    return dict(n_finite=int(len(v)), n_unread=int((~np.isfinite(v_cm)).sum()), mode_cm=float(0.5 * (bins[k] + bins[k + 1])),
                median_cm=round(med, 3), nmad_cm=round(float(1.4826 * np.median(np.abs(v - med))), 3))


# ================================================================================================ figure 1
def fig1():
    site, unit, face = "B173nb_b10", "ALS", 1
    mdir = S2 / "measure" / site
    r = np.load(S1 / "defs" / site / f"rows_{unit}.npz")
    gen = (r["code"] == 2) & (r["kind"] == 1) & (~r["in_band_v2"]) & (r["slope"].astype(np.float64) <= 17.0) & r["thin"]
    gen_idx = np.nonzero(gen)[0]
    curves = [("본 방법 씨앗 0", "prop_ALS_s0", "S2/measure"), ("본 방법 씨앗 1", "prop_ALS_s1", "S2/measure"),
              ("판 A", "fixA_ALS_s0", "this task (FT/measure, to be written by the same reading)"),
              ("허용 구간 없애기", "abl_band_ALS_s0", "S2/measure"), ("학습 전 사전 정보", "samepath_ALS", "S2/measure")]
    same = {}
    for res in ("prop_ALS_s0", "prop_ALS_s1", "abl_band_ALS_s0", "samepath_ALS", "surface_ALS"):
        f = mdir / f"{unit}__{res}.npz"
        same[res] = bool(np.array_equal(np.load(f)["gentle_row"], gen_idx))           # only the row-index array is read here
    check("fig1 gentle rows (measure_s2.py:93 rule) == 'gentle_row' of every stage-2 measure file of the curves", all(same.values()), files=same)
    sel = r["surf_ext"][gen_idx] == face
    rows = gen_idx[sel]
    pos = np.nonzero(sel)[0]
    check("fig1 rows of face 1 == 32,932 (order 11.2, stage-2 decision-6 figure)", len(rows) == 32932, rows=int(len(rows)))
    s2fig = json.loads((S2 / "figs/band_B173.json").read_text())
    prior_mode_s2 = s2fig["curves"]["학습 전 항공 LiDAR"]["mode_cm"]     # only 'rows' and the pre-training prior curve's mode are used
    check("fig1 rows == the stage-2 figure json 'rows'", int(s2fig["rows"]) == len(rows), stage2=int(s2fig["rows"]))
    X = gt_xyz(site)
    P = rows_xyz(r, X)
    zgt_m = np.load(mdir / f"{unit}__surface_ALS.npz")["zgt"]
    check("fig1 measure 'zgt' == GT z of the gentle rows (P[:, 2])", np.array_equal(zgt_m, P[gen_idx, 2]))
    # the reading: re-read 'new' of the registered prior surface (surface_ALS, an input) on 2,000 rows with the stage-2 code
    sys.path.insert(0, "/repo/scripts/phd/main_stage1_diag_v1")
    sys.path.insert(0, "/repo/scripts/phd/main_stage1_v1")
    from diag_mesh import WIN, Scene, readings
    z = np.load(S1 / "defs" / site / f"prior_{unit}.npz")
    sc = Scene(z["V"].astype(np.float64), z["F"].astype(np.int64))
    rng = np.random.default_rng(0)
    pick = np.sort(rng.choice(len(rows), 2000, replace=False))
    Q = P[rows[pick]]
    splits, zz, tri = sc.vertical_all(Q[:, :2])
    cnt, cur, a, b, ih, ia, ib = readings(splits, zz, Q[:, 2])
    stored = np.load(mdir / f"{unit}__surface_ALS.npz")["new"][pos[pick]]
    both = np.isfinite(b) & np.isfinite(stored)
    diff = float(np.abs(b[both] - stored[both]).max()) if both.any() else None
    ok = (diff is not None and diff <= 1e-6) and bool(np.array_equal(np.isfinite(b), np.isfinite(stored)))
    check("fig1 'new' re-read on the prior surface (2,000 rows, seed 0) == stored 'new' of surface_ALS (new = z_crossing - z_GT)", ok,
          max_abs_diff_m=diff, nan_pattern_equal=bool(np.array_equal(np.isfinite(b), np.isfinite(stored))))
    del sc
    # the anchor of the vertical lines: the pre-training prior readings (no training result is read)
    pr = {}
    for res, what in (("samepath_ALS", "학습 전 사전 정보(같은 경로 메시; 4.1 표의 이름)"), ("surface_ALS", "정합한 사전 정보 면(2단계 그림의 '학습 전 항공 LiDAR')")):
        v = 100.0 * np.load(mdir / f"{unit}__{res}.npz")["new"][pos]
        pr[res] = dict(what=what, **hist_mode(v), source=short(mdir / f"{unit}__{res}.npz"))
    check("fig1 histogram rule reproduces the stage-2 figure's prior mode (surface_ALS)", pr["surface_ALS"]["mode_cm"] == float(prior_mode_s2),
          here=pr["surface_ALS"]["mode_cm"], stage2=float(prior_mode_s2))
    np.savez_compressed(PREP / "figpos_fig1_rows.npz", rows=rows.astype(np.int64), pos_in_gentle=pos.astype(np.int64), gentle_row=gen_idx.astype(np.int64),
                        xyz_gt=P[rows])
    tau = float(np.median(r["tau"][rows]))
    return dict(
        see="판 A에서 결과의 봉우리가 사전 정보 쪽으로 옮겨 갔는가",
        case="B173 주변 · 항공 LiDAR", site=site, prior=unit, face_surf_ext=face, kind="distribution (one panel)",
        rows=dict(count=int(len(rows)), file="FT/prep/figpos_fig1_rows.npz",
                  file_keys=dict(rows="indices into S1/defs/B173nb_b10/rows_ALS.npz", pos_in_gentle="indices into the arrays of a measure npz "
                                 "(aligned with its 'gentle_row'): curve = 100 x new[pos_in_gentle]", gentle_row="the 35,345 gentle rows (measure_s2.py:93)",
                                 xyz_gt="GT point of each row (local frame)"),
                  rule="rows_ALS.npz: code == 2 & kind == 1 (roof-like) & ~in_band_v2 & slope <= 17 deg & thin (measure_s2.py:93), then surf_ext == 1 "
                       "(figs_s2.py:142-147 face_rows; figdefs 'band/B173nb_b10/ALS' face 1 = VIS-v1 scene 6)",
                  gentle_rows=int(len(gen_idx)), tau_m_median=round(tau, 5)),
        reading=dict(
            array="'new' of S2/measure/<site>/ALS__<result>.npz, one value per gentle row (aligned with 'gentle_row')",
            meaning="new = z of the highest crossing of the vertical line through the GT point (x, y) within z_GT +- 1 m, minus z_GT, in m "
                    "(scripts/phd/main_stage1_diag_v1/diag_mesh.py readings() '(b)', WIN = %.1f m; mesh crossings by Scene.vertical_all from "
                    "z = 250 m down). + = the result surface above the GT. NaN = no crossing within the window ('unread', counted apart, not in "
                    "the histogram)." % WIN,
            curve="value_cm = 100 x new[pos_in_gentle]; histogram bins 0.5 cm on [-15, 20] cm, values clipped into the range, y = share of the "
                  "finite rows (%) (figs_s2.band_B173)",
            mesh="the training-view TSDF mesh of the result (stage-2 measure_s2.load_mesh / result_paths); samepath_ALS = the prior through the "
                 "same path (S2 measured it); surface_ALS = the registered prior surface S1/defs/B173nb_b10/prior_ALS.npz",
            new_results="for fixA_ALS_s0 run the same reading (measure_s2.main: diag_mesh.Scene.vertical_all + readings on the gentle rows) into "
                        "this task's measure folder; its 'gentle_row' must equal figpos_fig1_rows.npz 'gentle_row'"),
        curves=[dict(name=n, result=res, measure=src) for n, res, src in curves],
        curves_note="the order's line list: 본 방법 두 씨앗, 판 A, 허용 구간 없애기, 학습 전 사전 정보. The stage-2 figure also drew MVS and used the "
                    "registered prior surface (surface_ALS) as '학습 전 항공 LiDAR'; here '학습 전 사전 정보' = samepath_ALS (order 4.1); "
                    "the two prior readings are recorded below. Every curve: same rows, same bins.",
        vertical_lines=dict(anchor="mode of the '학습 전 사전 정보' curve (samepath_ALS)", anchor_mode_cm=pr["samepath_ALS"]["mode_cm"],
                            offsets="anchor + w and anchor + tau, both sides (- and +)", tau_cm=round(100 * tau, 2), tau_source="order table A "
                            "(B173 주변 -> 탐색 지역 R2, 항공 LiDAR 14.70 cm) = rows_ALS.npz 'tau' of the rows",
                            w_source="item 1 table, row R2 · 항공 LiDAR (FT/prep/w1/R2_ALS.json); not read here"),
        prior_readings_pre_training=pr,
        panels=["하나"],
        under_figure="median and mode of each curve; rows 32,932 (thinned)",
    )


# ================================================================================================ figure 2
def fig2():
    site, prior = "R1rep_b10", "ALS"
    R = region(site, prior)
    Z = np.load(SL / "work/obs_masked" / f"region_{site}_{prior}.npz")
    ev = R["in_eval"].astype(bool)
    code = R["code_ext_v3"].astype(np.int64)
    obs = Z["obs"].astype(bool)
    viol = R["premise_violation"].astype(bool)
    within = R["obs_within_threshold"].astype(bool)
    img = (obs & ~(ev & viol)) | (ev & within)          # dm_common.Unit.img (scripts/phd/main_dist71_v1/dm_common.py:182)
    check("fig2 obs_masked row count == region file", len(obs) == len(code), obs=int(len(obs)), region=int(len(code)))
    pv, tau = R["premise_value"].astype(np.float64), R["tau"].astype(np.float64)
    w_re = (code == 3) & np.isfinite(pv) & (np.abs(pv) <= 2.0 * tau)
    check("fig2 obs_within_threshold == code 3 & |premise value (MVS - prior)| <= 2 tau (premise.split, k = 2 for ALS)", np.array_equal(w_re, within),
          recomputed=int(w_re.sum()), field=int(within.sum()))
    literal = obs | (ev & within)
    X = gt_xyz(site)
    r = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
    imp = dict(imported=False)
    try:
        sys.path.insert(0, "/repo/scripts/phd/main_dist71_v1")
        import dm_common as DMC
        DMC.S1 = S1                                     # dist71 ran with stage 1 at /out; here stage 1 is /s1
        u = DMC.Unit(site, prior, gt=SimpleNamespace(X=X))
        imp = dict(imported=True, equal=bool(np.array_equal(u.img, img)), unit_img=int(u.img.sum()))
        del u
    except Exception as e:  # noqa: BLE001
        imp = dict(imported=False, error=repr(e))
    check("fig2 '영상이 틀린 곳' here == dist71 dm_common.Unit(R1rep_b10, ALS).img (imported)", imp.get("equal", False), **imp)
    idx = np.nonzero(img)[0]
    C = R["centre"][idx].astype(np.float64)
    ncomp, lab = components(C, 0.36)
    area = np.bincount(lab, weights=R["area"][idx].astype(np.float64), minlength=ncomp)
    gtp = np.bincount(lab, weights=R["gt_points"][idx].astype(np.float64), minlength=ncomp)
    sus = np.bincount(lab, weights=R["gt_suspect"][idx].astype(np.float64), minlength=ncomp)
    eva = np.bincount(lab, weights=R["gt_suspect_evaluated"][idx].astype(np.float64), minlength=ncomp)
    npa = np.bincount(lab, minlength=ncomp)
    big = area >= 1.0
    one = big & (sus == 0)
    strict = one & (eva == npa)
    best = int(np.argmax(np.where(one, gtp, -1.0)))
    best_strict = int(np.argmax(np.where(strict, gtp, -1.0)))
    check("fig2 the choice is the same when every patch of the cluster must also be evaluated by the gt_suspect rule", best == best_strict,
          chosen=best, strict=best_strict)
    cand = []
    for k in np.argsort(-gtp):
        if not big[k]:
            continue
        mem = idx[lab == k]
        cand.append(dict(patches=int(npa[k]), area_m2=round(float(area[k]), 2), gt_points=int(gtp[k]), gt_suspect=int(sus[k]),
                         gt_suspect_evaluated=int(eva[k]), one_layer=bool(one[k]), codes=counts(code[mem]),
                         mean_centre=r3(R["centre"][mem].mean(0))))
    mem = np.sort(idx[lab == best])
    Cm = R["centre"][mem].astype(np.float64)
    c = Cm.mean(0)
    q = Cm[:, :2] - c[:2]
    ev_, evec = np.linalg.eigh(q.T @ q / len(q))
    t = evec[:, int(np.argmax(ev_))]
    t = t if (t[0] > 0 or (t[0] == 0 and t[1] > 0)) else -t
    t = t / np.linalg.norm(t)
    nrm = np.array([-t[1], t[0]])
    L, HW = 6.0, 0.25
    near_patch = int(mem[np.argmin(np.linalg.norm(Cm - c, axis=1))])
    sm, dm_ = q @ t, q @ nrm
    # band members: GT points (all stage-1 GT, as figs_s2.section_fig), region rows, patches
    Gall = np.concatenate([X[k] for k in sorted(X)])
    s_g = (Gall[:, :2] - c[:2]) @ t
    d_g = (Gall[:, :2] - c[:2]) @ nrm
    gin = np.nonzero((np.abs(s_g) <= L) & (np.abs(d_g) <= HW))[0]
    P = rows_xyz(r, X)
    s_r = (P[:, :2] - c[:2]) @ t
    d_r = (P[:, :2] - c[:2]) @ nrm
    rin = np.nonzero((np.abs(s_r) <= L) & (np.abs(d_r) <= HW))[0]
    s_p = (R["centre"][:, :2] - c[:2]) @ t
    d_p = (R["centre"][:, :2] - c[:2]) @ nrm
    pin = np.nonzero((np.abs(s_p) <= L) & (np.abs(d_p) <= HW))[0]
    zm = r["z_mvs"][rin].astype(np.float64)
    zprior = R["centre"][pin, 2].astype(np.float64)
    zm = zm[np.isfinite(zm)]
    pz = np.load(S1 / "defs" / site / f"prior_{prior}.npz")
    pseg = plane_segments(*crop_mesh(pz["V"].astype(np.float64), pz["F"].astype(np.int64), c, L + 5), c, np.array([t[0], t[1], 0.0]), L)
    zall = np.concatenate([Gall[gin, 2], zprior, zm, pseg[..., 1].ravel()])
    lo, hi = float(np.percentile(zall, 1) - 0.6), float(np.percentile(zall, 99) + 0.6)
    inmem = np.isin(pin, mem)
    np.savez_compressed(PREP / "figpos_fig2_rows.npz", gt_index=gin.astype(np.int64), gt_s=s_g[gin], gt_d=d_g[gin], gt_z=Gall[gin, 2],
                        row_index=rin.astype(np.int64), row_s=s_r[rin], row_z=P[rin, 2], row_thin=r["thin"][rin], row_patch=r["patch"][rin].astype(np.int64),
                        patch_index=pin.astype(np.int64), patch_s=s_p[pin], patch_d=d_p[pin], patch_z=R["centre"][pin, 2], cluster_patches=mem.astype(np.int64),
                        prior_segments=pseg)
    gm, pm, mg = (R["gt_med"][mem].astype(np.float64), R["premise_value"][mem].astype(np.float64), R["mvs_minus_gt_at_gt"][mem].astype(np.float64))
    return dict(
        see="영상이 틀린 곳에서 판 A가 결과를 맞는 사전 정보 쪽으로 당겼는가",
        case="R1 · 항공 LiDAR", site=site, prior=prior, kind="section (two panels)",
        place=dict(
            name="영상이 틀린 곳",
            rule="dist71 dm_common.Unit.img = (obs_masked 'obs' & ~(in_eval & premise_violation)) | (in_eval & obs_within_threshold): the fill "
                 "task's filtered image-error patches without the code-3 premise-violation patches, plus the code-3 patches with "
                 "|MVS - prior| (region 'premise_value') <= 2 tau (scripts/phd/main_dist71_v1/dm_common.py:180-182; fill om.py:668-669, 938-940)",
            files=dict(region=short(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz"), obs_masked=short(SL / "work/obs_masked" / f"region_{site}_{prior}.npz")),
            patches=int(img.sum()), area_m2=round(float(R["area"][img].sum()), 2), codes=counts(code[img]), kinds=counts(R["kind"][img]),
            obs_patches=int(obs.sum()), within_threshold_patches=int((ev & within).sum()),
            literal_union_patches=int(literal.sum()),
            literal_union_note="obs | within (without removing premise violations) has %d patches; the %d more are obs patches that are code-3 "
                               "premise violations (|MVS - prior| > 2 tau = '전제 위배', order 4.4), so the dist71 definition is used"
                               % (int(literal.sum()), int((literal & ~img).sum()))),
        clusters=dict(
            link="patch centres (region 'centre', 3-D) within 0.36 m joined (cKDTree.query_pairs + connected components, as figdefs_s2.components "
                 "and the fill task's 'components')",
            keep="area (sum of region 'area') >= 1.0 m^2; GT one layer = no patch of the cluster has region 'gt_suspect' (the multi-layer GT flag "
                 "the fill task used: configs/phd/metrics_fix_v1/gt_suspect_rule_v1.json, double layer in the 0.25 m cell or >= 5 % multi-return "
                 "ULS points; evaluated on roof-like codes 2/3 with matched ULS points)",
            choose="the most GT points (sum of region 'gt_points'; equal to 'gt_n' here)",
            n_clusters=int(ncomp), n_area_ge_1=int(big.sum()), n_one_layer=int(one.sum()),
            candidates_area_ge_1=cand),
        chosen=dict(patches=int(len(mem)), area_m2=round(float(R["area"][mem].sum()), 3), gt_points=int(R["gt_points"][mem].sum()),
                    codes=counts(code[mem]), kinds=counts(R["kind"][mem]), gt_suspect=int(R["gt_suspect"][mem].sum()),
                    gt_suspect_evaluated=int(R["gt_suspect_evaluated"][mem].sum()), mean_centre=r3(c), nearest_patch=near_patch,
                    nearest_patch_centre=r3(R["centre"][near_patch]),
                    extent_along_s_m=[round(float(sm.min()), 3), round(float(sm.max()), 3)], extent_across_d_m=[round(float(dm_.min()), 3), round(float(dm_.max()), 3)],
                    gt_minus_prior_median_cm=round(100 * float(np.median(gm)), 2), mvs_minus_prior_median_cm=round(100 * float(np.median(pm)), 2),
                    mvs_minus_gt_median_cm=round(100 * float(np.median(mg)), 2), tau_cm=round(100 * float(np.median(R["tau"][mem])), 2),
                    patch_list=mem.tolist()),
        section=dict(centre_xyz=r3(c), direction_t_xy=[round(float(t[0]), 6), round(float(t[1]), 6)], across_n_xy=[round(float(nrm[0]), 6), round(float(nrm[1]), 6)],
                     length_m=12.0, half_length_m=L, width_m=0.5, half_width_m=HW,
                     rule="s = (xy - centre) . t in [-6, 6] m, d = (xy - centre) . n in [-0.25, 0.25] m; t = principal axis (largest eigenvector of "
                          "the plan covariance) of the cluster's patch centres, sign x >= 0; centre = mean of the cluster's patch centres",
                     principal_axis_eigenvalues_m2=[round(float(v), 4) for v in sorted(ev_, reverse=True)],
                     elongation=round(float(np.sqrt(max(ev_) / max(min(ev_), 1e-12))), 2),
                     z_range_m=[round(lo, 3), round(hi, 3)],
                     z_rule="percentile 1 - 0.6 m and percentile 99 + 0.6 m of the inputs in the band: the GT points, the prior (patch centres and the "
                            "registered prior surface S1/defs/R1rep_b10/prior_ALS.npz cut by the section plane) and the MVS (rows 'z_mvs'); the stage-2 "
                            "section rule (figs_s2.section_fig) without any result mesh; a result outside is drawn clipped at the frame",
                     z_inputs_min_max=dict(gt=[round(float(Gall[gin, 2].min()), 3), round(float(Gall[gin, 2].max()), 3)] if len(gin) else None,
                                           prior_patch_centres=[round(float(zprior.min()), 3), round(float(zprior.max()), 3)] if len(zprior) else None,
                                           mvs_rows=[round(float(zm.min()), 3), round(float(zm.max()), 3)] if len(zm) else None),
                     gt_points_in_band=int(len(gin)), gt_source="all stage-1 GT points S1/defs/R1rep_b10/gt_classes.npz 'xyz_gt_points' (figs_s2.gt_points)",
                     region_rows_in_band=dict(all=int(len(rin)), thinned=int(r["thin"][rin].sum())),
                     patches_in_band=dict(count=int(len(pin)), codes=counts(code[pin]), of_cluster=int(inmem.sum()), image_error=int(img[pin].sum()),
                                          list=pin.tolist()),
                     prior_surface_segments=int(len(pseg)),
                     file="FT/prep/figpos_fig2_rows.npz (gt_index into xyz_gt_points, row_index into rows_ALS.npz, patch_index into the region file, "
                          "s / d / z of each, cluster_patches, prior_segments (s, z))"),
        panels=[dict(label="(가)", name="본 방법 씨앗 0", result="prop_ALS_s0", mesh="S1/stage1/R1rep_b10/prop_ALS_s0/post/mesh_tsdf.ply"),
                dict(label="(나)", name="판 A", result="fixA_ALS_s0", mesh="FT/runs/R1rep_b10/fixA_ALS_s0/post/mesh_tsdf.ply (ft_common result_paths)")],
        in_every_panel=dict(gt="GT points of the band (grey dots)", prior=dict(name="학습 전 사전 정보", result="samepath_ALS",
                                                                              mesh="S1/stage1/R1rep_b10/samepath_ALS/mesh.ply (metrics_s1.result_paths)")),
        same_in_panels="same section, same s range [-6, 6] m, same z range",
        note="판 A is trained on this case only if it passes the gate (일 3); otherwise panel (나) is '학습하지 않음'",
    )


# ================================================================================================ figure 3
def fig3():
    site, prior = "R1rep_b10", "LoD2"
    R = region(site, prior)
    U = np.load(S0 / "s61/box" / site / prior / "units.npz")
    st = np.load(S0 / "fork_inputs/s61" / site / f"store_{prior}.npz")
    code = R["code_ext_v3"].astype(np.int64)
    n = len(code)
    order = dict(region_rows=int(n), store_loc_area=int(len(st["loc_area"])), units_loc_center=int(len(U["loc_center"])),
                 centre_equal_store=bool(np.array_equal(R["centre"], st["loc_center"])), state_equal_store=bool(np.array_equal(R["state"], st["state_data"])),
                 area_equal_store=bool(np.array_equal(R["area"], st["loc_area"])), kind_equal_store=bool(np.array_equal(R["kind"], st["loc_kind"])),
                 surf_ext_equal_store=bool(np.array_equal(R["surf_ext"], st["surf_ext"][st["loc_surface"]])),
                 centre_equal_units=bool(np.array_equal(R["centre"], U["loc_center"])))
    ok = all(v for k, v in order.items() if isinstance(v, bool)) and order["region_rows"] == order["store_loc_area"] == order["units_loc_center"]
    check("fig3 patch order: region file == stage-0 store (fork input) == units, row count and per-patch arrays", ok, **order)
    m = R["in_eval"].astype(bool) & np.isin(code, (4, 13))
    idx = np.nonzero(m)[0]
    C = R["centre"][idx]
    ext = [float(C[:, 0].min() - 3), float(C[:, 1].min() - 3), float(C[:, 0].max() + 3), float(C[:, 1].max() + 3)]
    locf = OUT / "checks/dry/r16B_R1rep_b10_LoD2/model/monitor/locations.npz"
    chg = dict(source="FT/checks/dry/r16B_R1rep_b10_LoD2/model/monitor/locations.npz", key="own_depth_changed", exists=locf.exists())
    changed = None
    if locf.exists():
        Lz = np.load(locf)
        chg.update(sha(locf))
        if "own_depth_changed" in Lz.files and len(Lz["own_depth_changed"]) == n:
            ch = Lz["own_depth_changed"].astype(bool)
            al = dict(rows=int(len(Lz["state"])), state_equal_region=bool(np.array_equal(Lz["state"], R["state"])),
                      centre_max_abs_diff_m=float(np.abs(Lz["center"].astype(np.float64) - R["centre"]).max()),
                      area_equal_region=bool(np.allclose(Lz["area"], R["area"])), kind_equal_region=bool(np.array_equal(Lz["kind"], R["kind"])),
                      surface_equal_region=bool(np.array_equal(Lz["surface_ext"], R["surf_ext"])))
            check("fig3 dry locations.npz (r16B) aligned with the region file (state, centre within 1 mm, area, kind, surface)",
                  al["state_equal_region"] and al["centre_max_abs_diff_m"] <= 1e-3 and al["area_equal_region"] and al["kind_equal_region"] and al["surface_equal_region"], **al)
            d16 = OUT / "checks/dry/r16d_R1rep_b10_LoD2/model/monitor/locations.npz"
            if d16.exists():
                Dz = np.load(d16)
                same = bool(np.array_equal(ch, Dz["unit_judgment"] != Lz["unit_judgment"]))
                check("fig3 own_depth_changed == patches whose unit_judgment differs between r16 defaults (r16d) and 판 B (r16B)", same)
                chg["equals_r16d_vs_r16B_unit_judgment_difference"] = same
                chg["judgment_before_to_after_on_missing"] = {f"{a}->{b}": int(v) for (a, b), v in sorted(
                    Counter(zip(Lz["judgment_before_own_depth"][idx].tolist(), Lz["judgment"][idx].tolist())).items())}
            changed = ch[idx]
            chg.update(alignment=al, unit_total=int(ch.sum()), unit_states=counts(Lz["state"][ch]), in_figure=int(changed.sum()),
                       in_figure_by_code=counts(code[idx][changed]), in_figure_by_code_kind={f"{a}/{b}": int(v) for (a, b), v in sorted(
                           Counter(zip(code[idx][changed].tolist(), R["kind"][idx][changed].tolist())).items())})
        else:
            chg["problem"] = "key missing or length differs"
            check("fig3 own_depth_changed present with the region's length", False)
    rows = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
    th = rows["thin"].astype(bool)
    pa = rows["patch"]
    thin_n = np.bincount(pa[th], minlength=n)
    by = {}
    for cc in (4, 13):
        mm = idx[code[idx] == cc]
        by[str(cc)] = dict(patches=int(len(mm)), area_m2=round(float(R["area"][mm].sum()), 3), gt_points=int(R["gt_points"][mm].sum()),
                           gt_rows_thin=int(thin_n[mm].sum()), kinds=counts(R["kind"][mm]), surf_ext=counts(R["surf_ext"][mm]),
                           changed_in_item2=(int(changed[code[idx] == cc].sum()) if changed is not None else None))
    nc, lab = components(C, 1.0)
    groups = []
    for k in range(nc):
        g = idx[lab == k]
        cg = R["centre"][g]
        groups.append(dict(patches=int(len(g)), codes=counts(code[g]), kinds=counts(R["kind"][g]), surf_ext=counts(R["surf_ext"][g]),
                           extent_xy_plus1m=[round(float(cg[:, 0].min() - 1), 2), round(float(cg[:, 1].min() - 1), 2),
                                             round(float(cg[:, 0].max() + 1), 2), round(float(cg[:, 1].max() + 1), 2)]))
    groups.sort(key=lambda g: -g["patches"])
    plist = dict(index=idx.tolist(), code=code[idx].tolist(), kind=R["kind"][idx].astype(int).tolist(), surf_ext=R["surf_ext"][idx].astype(int).tolist(),
                 area_m2=[round(float(a), 5) for a in R["area"][idx]], centre=[r3(x) for x in C], corners_xy=corners_xy(U, idx).tolist(),
                 gt_points=R["gt_points"][idx].astype(int).tolist(), gt_rows_thin=thin_n[idx].astype(int).tolist(),
                 changed_in_item2=(changed.astype(bool).tolist() if changed is not None else None))
    return dict(
        see="판 B에서 결측 패치가 사전 정보를 지켰는가, 대가는 어디에 생겼는가",
        case="R1 · LoD2", site=site, prior=prior, kind="plan map (two panels)",
        patches_rule="region file in_eval & code_ext_v3 in (4, 13) (평가 범위의 결측 패치, order 4.4)",
        region_file=short(S1 / "regions_v3" / f"regions_ext_v3_{site}_{prior}.npz"),
        counts=dict(all=int(len(idx)), area_m2=round(float(R["area"][idx].sum()), 3), by_code=by, by_code_kind={f"{a}/{b}": int(v) for (a, b), v in sorted(
            Counter(zip(code[idx].tolist(), R["kind"][idx].tolist())).items())}, states=counts(R["state"][idx])),
        extent_xy=[round(v, 2) for v in ext], extent_rule="box of the patch centres + 3 m (x, y local frame)",
        view="from above: x to the right, y up, equal scale; same extent in both panels",
        patch_list=plist,
        patch_list_note="corners_xy = plan corners of the 0.25 m patch (centre +- 0.125 t1 +- 0.125 t2 of S0/s61/box/R1rep_b10/LoD2/units.npz). A "
                        "wall-like patch (kind 2; %d of %d here) is vertical, so its plan footprint is a 0.25 m segment: draw it as a thick segment "
                        "(or a marker) so it stays visible" % (int((R["kind"][idx] == 2).sum()), int(len(idx))),
        colour_rule=dict(text="결과 면이 사전 정보 면 0.2 m 안 (one colour)",
                         reading="per patch: the 3-D distance from the patch centre (region 'centre', a point on the registered LoD2 face) to the "
                                 "result's training-view TSDF mesh (Open3D compute_distance = MeshScene.distance, the d_g operation of the new "
                                 "distance metric with the prior point in place of the GT point); coloured when <= 0.2 m, otherwise neutral",
                         same_colour_two_meanings="code 4 (prior right): coloured = good; code 13 (prior wrong): coloured = bad (past shape kept); "
                                                  "the patch counts and the coloured shares of the two codes are written apart under the figure"),
        outline="code-13 patches: outline", dot="patches whose reading changed in item 2 (own_depth_changed of the r16B dry judgment): dot",
        changed=chg,
        zoom_groups=dict(rule="the figure's patches joined at centre distance <= 1.0 m (3-D, the stage-2 map rule); each group's box + 1 m, for "
                              "enlarged insets if the map is too small (rule 10)", groups=groups),
        panels=[dict(label="(가)", name="본 방법 씨앗 0", result="prop_LoD2_s0", mesh="S1/stage1/R1rep_b10/prop_LoD2_s0/post/mesh_tsdf.ply"),
                dict(label="(나)", name="판 B", result="fixB_LoD2_s0", mesh="FT/runs/R1rep_b10/fixB_LoD2_s0/post/mesh_tsdf.ply (ft_common result_paths)")],
        under_figure="per code (4 and 13): patches, coloured share, for each panel",
    )


# ================================================================================================ figure 4
def fig4():
    site, prior = "B173nb_b10", "ALS"
    R = region(site, prior)
    U = np.load(S0 / "s61/box" / site / prior / "units.npz")
    W = np.load(SL / "work/undecidable" / f"regions_{site}_{prior}.npz")
    D = json.loads((SL / "prep/undecidable/definitions.json").read_text())
    FP = json.loads((SL / "prep/figpos/undecidable.json").read_text())
    code = R["code_ext_v3"].astype(np.int64)
    n = len(code)
    ev = R["in_eval"].astype(bool)
    case, band = W["case_skylight"].astype(bool), W["case_band_skylight"].astype(bool)
    check("fig4 undecidable masks row count == region file == units", len(case) == n == len(U["loc_center"]), masks=int(len(case)), region=int(n))
    check("fig4 region centre == units loc_center (patch order)", np.array_equal(R["centre"], U["loc_center"]))
    du = D["cases"]["skylight"]["units"][prior]
    check("fig4 case mask == definitions.json case_patch_list (fill task)", np.array_equal(np.nonzero(case)[0], np.sort(np.asarray(du["case_patch_list"]))),
          mask=int(case.sum()), listed=int(len(du["case_patch_list"])))
    check("fig4 band mask count == definitions.json band patches", int(band.sum()) == int(du["band"]["patches"]), mask=int(band.sum()), listed=int(du["band"]["patches"]))
    ext = [float(v) for v in FP["auxiliary"]["extent_xy"]]
    C = R["centre"]
    both = case | band
    bb = [float(C[both, 0].min()), float(C[both, 1].min()), float(C[both, 0].max()), float(C[both, 1].max())]
    inside = bb[0] >= ext[0] and bb[1] >= ext[1] and bb[2] <= ext[2] and bb[3] <= ext[3]
    check("fig4 case region + band of the ALS unit lie inside the undecidable_aux extent", inside, box=r3(bb), extent=ext)
    mis = both & ev & np.isin(code, (4, 13))
    idx = np.nonzero(mis)[0]
    inext = (C[:, 0] >= ext[0]) & (C[:, 0] <= ext[2]) & (C[:, 1] >= ext[1]) & (C[:, 1] <= ext[3])
    other = np.nonzero(inext & ev & np.isin(code, (4, 13)) & ~both)[0]
    sus_f, sus_e = int(R["gt_suspect"][case].sum()), int(R["gt_suspect_evaluated"][case].sum())
    ml = du["multi_layer_gt"]
    check("fig4 multi-layer GT share of the ALS case region == the fill task's 24 / 163", (sus_f, sus_e) == (int(ml["multi_layer"]), int(ml["evaluated"])),
          here=[sus_f, sus_e], fill=[int(ml["multi_layer"]), int(ml["evaluated"])])
    rows = np.load(S1 / "defs" / site / f"rows_{prior}.npz")
    th = rows["thin"].astype(bool)
    rsel = np.nonzero(th & np.isin(rows["patch"], idx))[0]
    thin_n = np.bincount(rows["patch"][th], minlength=n)
    mc = C[idx]
    zoom = [float(mc[:, 0].min() - 1.5), float(mc[:, 1].min() - 1.5), float(mc[:, 0].max() + 1.5), float(mc[:, 1].max() + 1.5)]
    area_case, area_band, area_mis = float(R["area"][case].sum()), float(R["area"][band].sum()), float(R["area"][idx].sum())
    by = {str(cc): dict(patches=int((code[idx] == cc).sum()), area_m2=round(float(R["area"][idx][code[idx] == cc].sum()), 4),
                        gt_points=int(R["gt_points"][idx][code[idx] == cc].sum()), gt_rows_thin=int(thin_n[idx][code[idx] == cc].sum()))
          for cc in (4, 13)}
    return dict(
        see="유리 채광창 둘레의 결측 패치가 판 B에서 채워졌는가",
        case="B173 주변 · 항공 LiDAR", site=site, prior=prior, kind="plan map (two panels)",
        extent_xy=ext, extent_source="SL/prep/figpos/undecidable.json 'auxiliary' extent_xy (the fill task's undecidable_aux view, drawn there for "
                                     "LoD2: the LoD2 case box + 3 m); the same view is used for the ALS unit",
        view="from above: x to the right, y up, equal scale; same extent in both panels",
        case_region=dict(source="SL/work/undecidable/regions_B173nb_b10_ALS.npz 'case_skylight' (= definitions.json cases.skylight.units.ALS "
                                "case_patch_list)", patches=int(case.sum()), area_m2=round(area_case, 3), codes=counts(code[case]),
                         box_xy=r3([C[case, 0].min(), C[case, 1].min(), C[case, 0].max(), C[case, 1].max()]), patch_list=np.nonzero(case)[0].tolist(),
                         rule="kept premise-violation components (>= 1 m^2, centres joined at 0.36 m) with a patch on the place B173_glass_gutters "
                              "(definitions.json rules 'components', 'case_place', 'case_region')"),
        band=dict(source="SL/work/undecidable/regions_B173nb_b10_ALS.npz 'case_band_skylight'", rule="definitions.json rules 'band_2m' / "
                  "'case_band': patches within 2 m (3-D centre distance) of the case region, premise-violation patches excluded",
                  patches=int(band.sum()), area_m2=round(area_band, 3), codes=counts(code[band]), patch_list=np.nonzero(band)[0].tolist()),
        place_box_xy=r3(bb),
        missing=dict(rule="case region | band, in_eval, code_ext_v3 in (4, 13)", patches=int(len(idx)), by_code=by, area_m2=round(area_mis, 4),
                     index=idx.tolist(), code=code[idx].tolist(), area=[round(float(a), 5) for a in R["area"][idx]], centre=[r3(x) for x in mc],
                     corners_xy=corners_xy(U, idx).tolist(), in_case=case[idx].astype(bool).tolist(), states=counts(R["state"][idx]),
                     gt_points=R["gt_points"][idx].astype(int).tolist(), gt_rows_thin=thin_n[idx].astype(int).tolist(),
                     gt_row_index_thin=rsel.tolist(), box_xy=r3([mc[:, 0].min(), mc[:, 1].min(), mc[:, 0].max(), mc[:, 1].max()]),
                     share_of_place_area=round(area_mis / (area_case + area_band), 4)),
        missing_in_extent_outside_place=dict(note="missing patches inside the extent but outside the case region and band: not coloured (drawn as "
                                                  "'outside the place')", patches=int(len(other)), codes=counts(code[other]), index=other.tolist()),
        colour_rule=dict(text="결측 패치의 결과 면이 참값 0.2 m 안 (one colour)",
                         reading="the thinned GT rows (rows_ALS.npz 'thin') of the missing patches, each coloured when |d_g| <= 0.2 m, d_g = 3-D "
                                 "distance from the GT point to the result's training-view TSDF mesh (MeshScene.distance; the same d_g as "
                                 "결측 R(0.2 m), dist71 d2_dist r_d); per patch the share of its rows within 0.2 m may be written",
                         outline="case region outline (solid) and 2 m band outline (dashed) as in the fill task's figure",
                         excluded="patches outside the evaluation range in a grey other than 'none' (rule 9)"),
        multi_layer_gt=dict(rule=ml["rule"], case_region=dict(flagged=sus_f, evaluated=sus_e, share=round(sus_f / max(sus_e, 1), 4)),
                            band=dict(flagged=int(R["gt_suspect"][band].sum()), evaluated=int(R["gt_suspect_evaluated"][band].sum())),
                            missing_patches="not evaluated (the rule covers roof-like codes 2 and 3 only)",
                            caption="참값이 여러 층일 수 있는 몫: 사례 영역 %d / %d = %.1f %%" % (sus_f, sus_e, 100.0 * sus_f / max(sus_e, 1))),
        zoom_candidate=dict(extent_xy=[round(v, 2) for v in zoom], rule="box of the missing patches' centres + 1.5 m: an enlarged inset if the "
                            "change is small (rule 10); the missing patches are %.2f %% of the area of the case region + band" % (100 * area_mis / (area_case + area_band))),
        panels=[dict(label="(가)", name="본 방법 씨앗 0", result="prop_ALS_s0", mesh="S0/stage0/b1_ALS/post/mesh_tsdf.ply (B173 주변 stage-1 method = "
                     "stage-0 run b1_ALS; s3_common.run_dir)"),
                dict(label="(나)", name="판 B", result="fixB_ALS_s0", mesh="FT/runs/B173nb_b10/fixB_ALS_s0/post/mesh_tsdf.ply (ft_common result_paths)")],
        under_figure="the coloured share of the GT rows per code (4 and 13) and the rows counted; the multi-layer GT share of the case region (rule 5)",
    )


# ================================================================================================ figures 0 and 5 (no place)
def fig0():
    return dict(
        see="참값 없이 나눈 두 몫이 참값과 같은 쪽을 가리키는가", kind="bars (one panel); no place",
        rows="the nine rows of the item-1 table: search regions B0, R2, R1 x LoD2 roof faces, LoD2 wall faces, 항공 LiDAR",
        bars="per row, side by side: the image share and the prior share found without GT (sigma_image, sigma_prior) next to the two shares found "
             "with GT (NMAD of MVS - GT and of prior - GT, the gate's values outside the evaluation box; the whole search region when fewer than "
             "1,000 GT patches lie outside, written so)",
        above_bars="tau and w of the row", unsplit="a row where sigma_image >= NMAD is written '나누지 못함' (w = tau)",
        source="FT/prep/w1/<search region>_<prior>.json (item 1)", panels=["하나"])


def fig5():
    return dict(
        see="두 판이 어디서 얼마나 바꾸었는가", kind="bars per case (six cases); no place",
        panels=[dict(label="(가)", value="두 자료가 모두 맞는 곳(코드 2)의 거리", fix="판 A", result="fixA_<prior>_s0"),
                dict(label="(나)", value="결측 R(0.2 m) (코드 4)", fix="판 B", result="fixB_<prior>_s0"),
                dict(label="(다)", value="결측 영역의 과거 형상 유입률 (코드 13)", fix="판 B", result="fixB_<prior>_s0")],
        bars="per case: the fix's value minus the mean of the 본 방법 two seeds (order 9.2: the basis of comparison)",
        criterion_band="the criterion of order 9.2 drawn as a band around 0: +- criterion and +- 2 x criterion (같음 / 가능·근거 불완전 / 확인); "
                       "criterion = the largest of the pooled spread, the case's spread 2.8 x |seed 0 - seed 1| / sqrt 2, and 300 / samples for a share",
        not_drawn="a case where the fix was not trained (판 A stopped by the gate) or the samples are < 100 ('표본 부족') gets no bar, its name written",
        cases=["B0 · LoD2", "B0 · 항공 LiDAR", "B173 주변 · LoD2", "B173 주변 · 항공 LiDAR", "R1 · LoD2", "R1 · 항공 LiDAR"])


def training_state():
    runs = OUT / "runs"
    items = sorted(p.name for p in runs.iterdir()) if runs.exists() else []
    trained = [str(p.relative_to(OUT)) for p in runs.rglob("model")] if runs.exists() else []
    return dict(runs_dir="FT/runs", entries=items, model_dirs=trained), not trained


def panel_meshes(figs):
    """the existing panels' meshes (earlier results and the pre-training prior) exist; this task's results are only named (not trained yet)."""
    have = {}
    for k, f in figs.items():
        meshes = [p["mesh"] for p in f.get("panels", []) if isinstance(p, dict) and "mesh" in p]
        if isinstance(f.get("in_every_panel"), dict):
            meshes.append(f["in_every_panel"]["prior"]["mesh"])
        for m in meshes:
            rel = m.split(" ")[0]
            if rel.startswith("FT/"):
                continue
            root = {"S1/": S1, "S0/": S0}[rel[:3]]
            have[rel] = (root / rel[3:]).exists()
    check("panel meshes of the earlier results and of the pre-training prior exist (paths only, not read)", all(have.values()), meshes=have)


def main():
    PREP.mkdir(parents=True, exist_ok=True)
    state, before = training_state()
    check("no training of this task has started (FT/runs has no model folder)", before, **state)
    figs = {}
    for k, f in (("fig0", fig0), ("fig1", fig1), ("fig2", fig2), ("fig3", fig3), ("fig4", fig4), ("fig5", fig5)):
        log("start", k)
        figs[k] = f()
        log("done", k)
    panel_meshes(figs)
    state2, before2 = training_state()
    inputs = [S1 / "regions_v3/regions_ext_v3_R1rep_b10_ALS.npz", S1 / "regions_v3/regions_ext_v3_R1rep_b10_LoD2.npz",
              S1 / "regions_v3/regions_ext_v3_B173nb_b10_ALS.npz", SL / "work/obs_masked/region_R1rep_b10_ALS.npz",
              SL / "work/undecidable/regions_B173nb_b10_ALS.npz", SL / "prep/undecidable/definitions.json", SL / "prep/figpos/undecidable.json",
              S2 / "measure/B173nb_b10/ALS__prop_ALS_s0.npz", S2 / "measure/B173nb_b10/ALS__surface_ALS.npz",
              S2 / "measure/B173nb_b10/ALS__samepath_ALS.npz", S1 / "defs/B173nb_b10/rows_ALS.npz", S1 / "defs/R1rep_b10/rows_ALS.npz",
              S1 / "defs/R1rep_b10/rows_LoD2.npz", S0 / "fork_inputs/s61/R1rep_b10/store_LoD2.npz"]
    out = dict(
        version="figpos_ft_v1", task_id="PHD-MAIN-FIXTEST-v1", order_section="11.2", written=now(), written_before_any_training=bool(before and before2),
        training_state=dict(at_start=state, at_end=state2),
        script="scripts/phd/main_fixtest_v1/figpos_ft.py", runner="CPUS=8 MEM=24 bash scripts/phd/main_fixtest_v1/run_cpu_ft.sh figpos figpos_ft.py",
        rule="order 11.2: the place, viewpoint and panels of each figure fixed before training from the region files and the GT only; no value of "
             "any training result is used (figure 1 uses, of the stage-2 measure files, only 'gentle_row', 'zgt' and the 'new' reading of the two "
             "pre-training prior meshes, and of the stage-2 figure json only 'rows' and the prior curve's mode; figure 3 uses this task's "
             "pre-training dry judgment of r16B). Nothing here is a result.",
        frame="x = E - %.0f, y = N - %.0f (EPSG:25832), z = the site's local height (the region files' frame)" % OFFSET,
        names=dict(prop="본 방법 (stage-1 r12), prop_<prior>_s0 / _s1", fixA="판 A, fixA_<prior>_s0", fixB="판 B, fixB_<prior>_s0",
                   samepath="학습 전 사전 정보, samepath_<prior>", abl_band="허용 구간 없애기 (stage 2), abl_band_ALS_s0 at B173nb_b10"),
        figures=figs, checks=CHECKS, all_checks_ok=all(c["ok"] for c in CHECKS),
        inputs=[sha(p) for p in inputs if Path(p).exists()],
        outputs={k: sha(PREP / k) for k in ("figpos_fig1_rows.npz", "figpos_fig2_rows.npz")},
        seconds=round(time.time() - T0, 1), scientific_verdict=None)

    def conv(o):
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, Path):
            return str(o)
        raise TypeError(type(o))
    (PREP / "figpos.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=conv))
    log("written", PREP / "figpos.json", "checks ok" if out["all_checks_ok"] else "SOME CHECK FAILED")
    for c in CHECKS:
        print(("  ok   " if c["ok"] else "  FAIL ") + c["check"])


if __name__ == "__main__":
    main()
